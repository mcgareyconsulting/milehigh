"""Outlook (Microsoft Graph) client for Banana Boy.

Read-only counterpart to gmail_client.py: pulls recent inbox messages and
runs keyword searches against the user's Outlook mailbox so the LLM can
cite email context during a report deep dive.

Auth failures are swallowed (logged, [] returned) so chat keeps working
when a user revokes Outlook access.
"""
import requests

from app.auth.microsoft_tokens import MicrosoftAuthError, get_valid_access_token
from app.logging_config import get_logger

logger = get_logger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0/me"
REQUEST_TIMEOUT = 5
DEFAULT_SELECT = "id,subject,from,receivedDateTime,bodyPreview,webLink,conversationId"


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _summarize(message):
    sender = (message.get("from") or {}).get("emailAddress") or {}
    return {
        "id": message.get("id"),
        "conversation_id": message.get("conversationId"),
        "from": f"{sender.get('name', '')} <{sender.get('address', '')}>".strip(),
        "subject": message.get("subject", ""),
        "preview": (message.get("bodyPreview") or "").strip(),
        "received_at": message.get("receivedDateTime"),
        "web_link": message.get("webLink"),
    }


def fetch_recent_messages(user_id, max_results=10):
    """Return the most recent inbox messages as compact summaries.

    Returns [] (logged) on any auth failure or HTTP error.
    """
    try:
        token = get_valid_access_token(user_id)
    except MicrosoftAuthError as exc:
        logger.info("outlook_skip_no_valid_token", user_id=user_id, error=str(exc))
        return []

    params = {
        "$top": max_results,
        "$select": DEFAULT_SELECT,
        "$orderby": "receivedDateTime desc",
    }
    try:
        resp = requests.get(
            f"{GRAPH_API_BASE}/mailFolders/Inbox/messages",
            params=params,
            headers=_headers(token),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("outlook_recent_failed", user_id=user_id, error=str(exc))
        return []

    return [_summarize(m) for m in resp.json().get("value", []) or []]


def search_messages(user_id, query, max_results=10):
    """Run a Graph $search against the user's mailbox.

    `query` is a free-text Graph KQL query (e.g. 'subject:RFI 042 OR body:"due today"').
    Returns [] on auth/HTTP error.
    """
    if not query:
        return []
    try:
        token = get_valid_access_token(user_id)
    except MicrosoftAuthError as exc:
        logger.info("outlook_skip_no_valid_token", user_id=user_id, error=str(exc))
        return []

    headers = _headers(token)
    # $search requires this header per Graph docs.
    headers["ConsistencyLevel"] = "eventual"
    params = {
        "$search": f'"{query}"',
        "$top": max_results,
        "$select": DEFAULT_SELECT,
    }
    try:
        resp = requests.get(
            f"{GRAPH_API_BASE}/messages",
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("outlook_search_failed", user_id=user_id, error=str(exc))
        return []

    return [_summarize(m) for m in resp.json().get("value", []) or []]


def get_message(user_id, message_id):
    """Fetch a single message including the full body (HTML)."""
    if not message_id:
        return None
    try:
        token = get_valid_access_token(user_id)
    except MicrosoftAuthError as exc:
        logger.info("outlook_skip_no_valid_token", user_id=user_id, error=str(exc))
        return None

    try:
        resp = requests.get(
            f"{GRAPH_API_BASE}/messages/{message_id}",
            headers=_headers(token),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(
            "outlook_get_message_failed", user_id=user_id,
            message_id=message_id, error=str(exc),
        )
        return None

    data = resp.json()
    summary = _summarize(data)
    body = data.get("body") or {}
    summary["body_content_type"] = body.get("contentType")
    summary["body"] = body.get("content")
    return summary
