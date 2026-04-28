"""Gmail client for Banana Boy.

Read side: `fetch_recent_threads` returns compact thread summaries the chat
handler injects into the system prompt. Auth failures are swallowed (logged,
[] returned) so chat keeps working when a user revokes Gmail access.

Write side: `create_draft` / `send_draft` create and send drafts. Sending
only ever happens via send_draft — never directly from arbitrary input —
so the LLM is forced to draft → confirm → send.

TODO(post-demo): replace the N+1 (threads list + per-thread metadata get)
with users.messages.list + batchGet for fewer round trips.
"""
import base64
from datetime import datetime, timezone
from email.mime.text import MIMEText

import requests

from app.auth.google_tokens import GoogleAuthError, get_valid_access_token
from app.logging_config import get_logger

logger = get_logger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
REQUEST_TIMEOUT = 5
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"


class GmailScopeError(RuntimeError):
    """Raised when the user's stored creds don't include the required scope."""


def _ensure_compose_scope(user_id):
    """Raise GmailScopeError if the user hasn't granted gmail.compose."""
    from app.models import GoogleCredentials

    creds = GoogleCredentials.get_for_user(user_id)
    if creds is None:
        raise GoogleAuthError("no google credentials")
    if GMAIL_COMPOSE_SCOPE not in (creds.scopes or "").split():
        raise GmailScopeError(
            "gmail.compose scope not granted — please reconnect Gmail to allow drafts/send."
        )


def _header(headers, name):
    for h in headers or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _format_internal_date(internal_date_ms):
    try:
        ms = int(internal_date_ms)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def fetch_recent_threads(user_id, max_results=10):
    """Return up to `max_results` thread summaries for `user_id`.

    Each item: {from, subject, snippet, internal_date}.
    Returns [] (logged) on any auth failure or HTTP error.
    """
    try:
        token = get_valid_access_token(user_id)
    except GoogleAuthError as exc:
        logger.info("gmail_skip_no_valid_token", user_id=user_id, error=str(exc))
        return []

    headers = {"Authorization": f"Bearer {token}"}

    try:
        list_resp = requests.get(
            f"{GMAIL_API_BASE}/threads",
            params={"maxResults": max_results},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        list_resp.raise_for_status()
        threads = list_resp.json().get("threads", []) or []
    except requests.RequestException as exc:
        logger.warning("gmail_threads_list_failed", user_id=user_id, error=str(exc))
        return []

    summaries = []
    for thread in threads:
        thread_id = thread.get("id")
        if not thread_id:
            continue
        try:
            t_resp = requests.get(
                f"{GMAIL_API_BASE}/threads/{thread_id}",
                params={
                    "format": "metadata",
                    "metadataHeaders": ["From", "Subject"],
                },
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            t_resp.raise_for_status()
            t_data = t_resp.json()
        except requests.RequestException as exc:
            logger.debug(
                "gmail_thread_get_failed",
                user_id=user_id, thread_id=thread_id, error=str(exc),
            )
            continue

        msgs = t_data.get("messages") or []
        if not msgs:
            continue
        first = msgs[0]
        msg_headers = first.get("payload", {}).get("headers", [])
        summaries.append({
            "from": _header(msg_headers, "From"),
            "subject": _header(msg_headers, "Subject"),
            "snippet": (first.get("snippet") or "").strip(),
            "internal_date": _format_internal_date(first.get("internalDate")),
        })

    return summaries


def _build_raw_message(to, subject, body, cc=None, bcc=None):
    """Return base64url-encoded RFC 2822 message ready for Gmail's `raw` field."""
    msg = MIMEText(body or "", "plain", "utf-8")
    msg["To"] = to or ""
    msg["Subject"] = subject or ""
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


def create_draft(user_id, to, subject, body, cc=None, bcc=None):
    """Create a Gmail draft. Returns {draft_id, message_id, to, subject, snippet}.

    Raises GmailScopeError if the user hasn't granted gmail.compose.
    Raises GoogleAuthError on auth failures (no creds / refresh failed).
    """
    _ensure_compose_scope(user_id)
    token = get_valid_access_token(user_id)

    raw = _build_raw_message(to, subject, body, cc=cc, bcc=bcc)
    resp = requests.post(
        f"{GMAIL_API_BASE}/drafts",
        json={"message": {"raw": raw}},
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code >= 400:
        logger.warning(
            "gmail_draft_create_failed",
            user_id=user_id, status=resp.status_code, body=resp.text[:300],
        )
        resp.raise_for_status()

    data = resp.json()
    draft_id = data.get("id")
    msg = data.get("message") or {}
    return {
        "draft_id": draft_id,
        "message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "to": to,
        "subject": subject,
        "snippet": (msg.get("snippet") or "").strip(),
    }


def send_draft(user_id, draft_id):
    """Send a previously-created draft. Returns {sent: True, message_id, thread_id}.

    Raises GmailScopeError if the user hasn't granted gmail.compose.
    Raises GoogleAuthError on auth failures.
    Raises RuntimeError with the Gmail API error body on HTTP failures.
    """
    _ensure_compose_scope(user_id)
    if not draft_id:
        raise ValueError("draft_id is required")
    token = get_valid_access_token(user_id)

    resp = requests.post(
        f"{GMAIL_API_BASE}/drafts/send",
        json={"id": draft_id},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code >= 400:
        body_text = resp.text[:500]
        logger.warning(
            "gmail_draft_send_failed",
            user_id=user_id, draft_id=draft_id,
            status=resp.status_code, body=body_text,
        )
        # Surface Google's error body so the chat tool can include it.
        try:
            err = resp.json().get("error", {})
            msg = err.get("message") or body_text
        except Exception:  # noqa: BLE001
            msg = body_text
        raise RuntimeError(f"Gmail API {resp.status_code}: {msg}")

    data = resp.json()
    return {
        "sent": True,
        "message_id": data.get("id"),
        "thread_id": data.get("threadId"),
    }
