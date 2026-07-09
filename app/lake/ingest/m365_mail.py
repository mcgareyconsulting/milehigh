"""Microsoft 365 mail → data lake (bronze) connector.

Pulls messages from the ingested mailbox set via the Graph app-only client and
lands them idempotently in RawSourceRecord. The mailbox set is admin-governed:
it's the membership of an Entra security group (the same group the
ApplicationAccessPolicy scopes the app to), so onboarding a mailbox is just
"admin adds it to the group." Falls back to an explicit list or the single
bb@mhmw.com forwarding mailbox.

`pull()` is the per-mailbox entry point for both triggers:
  - the scheduled poll across the set (since=watermark), via `poll()`;
  - an on-demand BB request ("read the email I forwarded you"), optionally with
    a Graph $search query and an explicit mailbox.
"""
import base64
import hashlib
import json
from datetime import datetime, timedelta

from flask import current_app

from app.brain.material_orders.attachments import build_attachment
from app.logging_config import get_logger
from app.microsoft.graph_app_client import graph_get
from app.models import LakeIngestState, RawSourceRecord, db

logger = get_logger(__name__)

SOURCE = "m365_mail"
RECORD_TYPE = "email"

# Fields pulled from Graph. `body` is the full HTML/text; the rest is envelope
# + threading metadata used for later normalization/entity-linking.
GRAPH_SELECT = (
    "id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,"
    "bodyPreview,body,conversationId,internetMessageId,hasAttachments,webLink"
)

# Re-read this far behind the watermark to absorb clock skew / late arrivals;
# (source, external_id) uniqueness makes the overlap harmless.
WATERMARK_OVERLAP = timedelta(minutes=5)
DEFAULT_MAX_RESULTS = 25


def _addr(recipient):
    """Graph recipient/emailAddress → {name, address(lowercased)}."""
    ea = (recipient or {}).get("emailAddress") or {}
    return {"name": ea.get("name", ""), "address": (ea.get("address") or "").lower()}


def _parse_graph_dt(value):
    """Graph ISO timestamp (e.g. '2026-06-06T18:30:00Z') → naive UTC datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _content_hash(payload):
    """sha256 over the stable content fields only.

    Excludes ingest/display metadata (webLink, previews) so the hash changes
    only when the message content itself changes. Attachment filenames+sizes are
    included so a message whose attachment lands late re-hashes and re-ingests.
    """
    basis = {k: payload.get(k) for k in (
        "external_id", "subject", "from", "to", "cc", "received_at",
        "conversation_id", "internet_message_id", "body",
    )}
    basis["attachments"] = [
        (a.get("filename"), a.get("size")) for a in (payload.get("attachments") or [])
    ]
    blob = json.dumps(basis, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _fetch_attachments(mailbox, message_id):
    """Pull a message's PDF attachments from Graph as payload attachment dicts.

    Graph returns fileAttachments with their base64 `contentBytes` inline on the
    attachments collection, so one JSON GET yields the bytes — no per-attachment
    `/$value` round trip. Non-PDF / reference attachments are skipped by
    build_attachment. Best-effort: a failure here logs and yields [] so the
    message still lands (text-only) rather than the whole poll aborting.
    """
    try:
        data = graph_get(f"/users/{mailbox}/messages/{message_id}/attachments")
    except Exception as exc:  # noqa: BLE001 — attachment fetch must never abort the poll
        logger.warning("m365_attachments_fetch_failed", message_id=message_id, error=str(exc))
        return []
    out = []
    for att in data.get("value", []) or []:
        if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
            continue
        content_b64 = att.get("contentBytes")
        if not content_b64:
            continue
        try:
            raw = base64.b64decode(content_b64)
        except (ValueError, TypeError):
            continue
        attachment = build_attachment(att.get("name"), att.get("contentType"), raw)
        if attachment:
            out.append(attachment)
    return out


def _normalize(message, mailbox):
    """Graph message JSON → (payload, external_pointer, occurred_at, content_hash)."""
    body = message.get("body") or {}
    payload = {
        "external_id": message.get("id"),
        "subject": message.get("subject", ""),
        "from": _addr(message.get("from")),
        "to": [_addr(r) for r in message.get("toRecipients") or []],
        "cc": [_addr(r) for r in message.get("ccRecipients") or []],
        "received_at": message.get("receivedDateTime"),
        "sent_at": message.get("sentDateTime"),
        "conversation_id": message.get("conversationId"),
        "internet_message_id": message.get("internetMessageId"),
        "preview": (message.get("bodyPreview") or "").strip(),
        "body_content_type": body.get("contentType"),
        "body": body.get("content"),
        "has_attachments": bool(message.get("hasAttachments")),
        "attachments": (
            _fetch_attachments(mailbox, message.get("id"))
            if message.get("hasAttachments") and message.get("id")
            else []
        ),
    }
    external_pointer = {
        "mailbox": mailbox,
        "web_link": message.get("webLink"),
    }
    occurred_at = _parse_graph_dt(message.get("receivedDateTime"))
    return payload, external_pointer, occurred_at, _content_hash(payload)


def _land(message, mailbox):
    """Upsert one Graph message into RawSourceRecord.

    Returns 'created' | 'updated' | 'unchanged'. Does not commit (caller does).
    """
    payload, external_pointer, occurred_at, content_hash = _normalize(message, mailbox)
    external_id = payload.get("external_id")
    if not external_id:
        logger.warning("m365_mail_skip_no_id")
        return "unchanged"

    existing = RawSourceRecord.query.filter_by(
        source=SOURCE, external_id=external_id
    ).first()

    if existing is None:
        db.session.add(RawSourceRecord(
            source=SOURCE,
            record_type=RECORD_TYPE,
            source_account=mailbox,
            external_id=external_id,
            content_hash=content_hash,
            occurred_at=occurred_at,
            payload=payload,
            external_pointer=external_pointer,
        ))
        return "created"

    if existing.content_hash != content_hash:
        existing.content_hash = content_hash
        existing.occurred_at = occurred_at
        existing.payload = payload
        existing.external_pointer = external_pointer
        # Content changed (e.g. a late-arriving attachment) — let the material-order
        # extractor look at it once more rather than trusting the prior scan.
        existing.material_order_scanned_at = None
        return "updated"

    return "unchanged"


def _mailbox():
    return current_app.config.get("BB_MAILBOX", "bb@mhmw.com")


def _group_member_mailboxes(group_id):
    """Enumerate mailbox addresses of a security group's transitive members."""
    mailboxes = []
    path = f"/groups/{group_id}/transitiveMembers"
    params = {"$select": "mail,userPrincipalName", "$top": 999}
    while path:
        data = graph_get(path, params=params)
        for member in data.get("value", []) or []:
            addr = (member.get("mail") or member.get("userPrincipalName") or "").lower()
            if addr:
                mailboxes.append(addr)
        path = data.get("@odata.nextLink")
        params = None  # nextLink already carries the query
    return mailboxes


def resolve_mailboxes():
    """The set of mailboxes to ingest.

    Priority: the admin-governed security group (members discovered via Graph) →
    an explicit BB_MAILBOXES comma list → the single BB_MAILBOX. Adding a mailbox
    to the group is picked up automatically on the next poll, no code/config change.
    """
    group_id = current_app.config.get("BB_INGEST_GROUP_ID")
    if group_id:
        return _group_member_mailboxes(group_id)
    raw = current_app.config.get("BB_MAILBOXES")
    if raw:
        return [m.strip().lower() for m in raw.split(",") if m.strip()]
    return [_mailbox()]


def pull(since=None, query=None, max_results=DEFAULT_MAX_RESULTS, mailbox=None):
    """Pull mail from the BB mailbox and land it in the lake (bronze).

    Args:
        since: only fetch messages received after this datetime (poll path).
        query: Graph KQL $search string (on-demand "find what I forwarded").
        max_results: page size ($top).
        mailbox: override the configured mailbox (mainly for tests).

    Returns a summary dict (counts + landed ids + max_occurred_at). Idempotent:
    re-pulling the same window lands 0 new rows.
    """
    mailbox = mailbox or _mailbox()
    params = {"$select": GRAPH_SELECT, "$top": max_results}
    if query:
        # Graph forbids combining $search with $orderby/$filter; search results
        # are relevance-ordered.
        params["$search"] = f'"{query}"'
    else:
        params["$orderby"] = "receivedDateTime desc"
        if since is not None:
            iso = since.replace(microsecond=0).isoformat() + "Z"
            params["$filter"] = f"receivedDateTime gt {iso}"

    data = graph_get(f"/users/{mailbox}/mailFolders/Inbox/messages", params=params)
    messages = data.get("value", []) or []

    counts = {"created": 0, "updated": 0, "unchanged": 0}
    landed_ids = []
    max_occurred = None
    for msg in messages:
        result = _land(msg, mailbox)
        counts[result] += 1
        if result in ("created", "updated"):
            landed_ids.append(msg.get("id"))
        occ = _parse_graph_dt(msg.get("receivedDateTime"))
        if occ and (max_occurred is None or occ > max_occurred):
            max_occurred = occ

    db.session.commit()
    logger.info(
        "m365_mail_pull", mailbox=mailbox, fetched=len(messages),
        created=counts["created"], updated=counts["updated"],
        unchanged=counts["unchanged"], search=bool(query),
    )
    return {
        "mailbox": mailbox,
        "fetched": len(messages),
        "created": counts["created"],
        "updated": counts["updated"],
        "unchanged": counts["unchanged"],
        "landed_ids": landed_ids,
        "max_occurred_at": max_occurred,
    }


def _poll_one(mailbox, max_results):
    """Incremental poll of one mailbox: pull since its watermark, then advance it."""
    state = LakeIngestState.get_or_create(SOURCE, account=mailbox)
    since = None
    if state.last_occurred_at is not None:
        since = state.last_occurred_at - WATERMARK_OVERLAP

    result = pull(since=since, max_results=max_results, mailbox=mailbox)

    state.last_polled_at = datetime.utcnow()
    max_occurred = result["max_occurred_at"]
    if max_occurred is not None and (
        state.last_occurred_at is None or max_occurred > state.last_occurred_at
    ):
        state.last_occurred_at = max_occurred
    db.session.commit()
    return result


def poll(max_results=DEFAULT_MAX_RESULTS):
    """Scheduled incremental poll across every mailbox in the ingested set.

    One mailbox failing (e.g. dropped from the access policy) doesn't abort the
    rest. Returns an aggregate summary plus the per-mailbox results.
    """
    agg = {"mailboxes": 0, "fetched": 0, "created": 0, "updated": 0, "unchanged": 0}
    per_mailbox = []
    for mailbox in resolve_mailboxes():
        try:
            result = _poll_one(mailbox, max_results)
        except Exception:
            db.session.rollback()  # discard this mailbox's pending state row
            logger.error("m365_mail_poll_mailbox_failed", mailbox=mailbox, exc_info=True)
            continue
        per_mailbox.append(result)
        agg["mailboxes"] += 1
        for key in ("fetched", "created", "updated", "unchanged"):
            agg[key] += result[key]
    agg["per_mailbox"] = per_mailbox
    return agg
