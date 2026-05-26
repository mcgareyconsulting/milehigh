"""
@milehigh-header
schema_version: 1
purpose: Normalize a CloudMailin inbound-email webhook payload into the provider-agnostic fields ingest_pickup_email expects.
exports:
  parse_inbound: Map CloudMailin's JSON body → {subject, sender, to, body, message_id, received_at}.
imports_from: [email.utils]
imported_by: [app/brain/job_log/routes (/brain/pickup/inbound-email)]
invariants:
  - Header lookup is case-insensitive and tolerant of CloudMailin format variants
    (message_id vs Message-ID), so a config change in the provider doesn't break parsing.
  - Sender/recipient prefer the SMTP envelope (authoritative) over the display headers.
  - message_id is the original email's Message-ID (stable across webhook retries) →
    used as the idempotency key by RecordPickupCommand. None if the email lacks one.
  - received_at is parsed from the Date header; None if absent/unparseable (caller defaults).
  - This is the ONLY CloudMailin-specific code; swapping providers means a sibling parser only.
"""
from email.utils import parsedate_to_datetime


def _headers_ci(headers) -> dict:
    """Lower-case-keyed copy of the headers object for case-insensitive lookup."""
    if not isinstance(headers, dict):
        return {}
    return {str(k).lower(): v for k, v in headers.items()}


def _first_header(headers_ci: dict, *names):
    """Return the first present header among the given (already-lowercased) names."""
    for name in names:
        val = headers_ci.get(name)
        if val:
            # CloudMailin may repeat a header as a list; take the first value.
            return val[0] if isinstance(val, list) else val
    return None


def parse_inbound(payload: dict) -> dict:
    """Normalize a CloudMailin inbound payload into ingest_pickup_email kwargs.

    CloudMailin's JSON shape:
        { "envelope": {"from": ..., "to": ..., "recipients": [...]},
          "headers":  {"subject": ..., "message_id": ..., "date": ..., "from": ..., "to": ...},
          "plain": "<text body>", "html": "...", "reply_plain": "..." }

    Returns {subject, sender, to, body, message_id, received_at}. Missing fields are
    None; the caller (ingest_pickup_email) decides how to handle an unparseable subject.
    """
    payload = payload or {}
    envelope = payload.get("envelope") or {}
    headers_ci = _headers_ci(payload.get("headers"))

    message_id = _first_header(headers_ci, "message-id", "message_id")

    date_value = _first_header(headers_ci, "date")
    received_at = None
    if date_value:
        try:
            received_at = parsedate_to_datetime(date_value)
        except (TypeError, ValueError):
            received_at = None

    body = payload.get("plain") or payload.get("reply_plain") or ""

    return {
        "subject": _first_header(headers_ci, "subject"),
        "sender": envelope.get("from") or _first_header(headers_ci, "from"),
        "to": envelope.get("to") or _first_header(headers_ci, "to"),
        "body": body,
        "message_id": message_id,
        "received_at": received_at,
    }
