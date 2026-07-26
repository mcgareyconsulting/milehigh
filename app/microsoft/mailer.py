"""Outbound email — the first send capability in this codebase (everything
else under app/microsoft/ and app/lake/ingest/m365_mail.py is inbound-only).

Sends app-only, as an explicit mailbox — the caller always states which
mailbox the mail goes out as (e.g. carmen_ai@mhmw.com for subcontractor
invites), never a silent default. This requires that mailbox be covered by the
app's Azure ApplicationAccessPolicy (same policy scope bb@mhmw.com already
uses — see docs/bb-email-ingestion.md); sending as a mailbox outside that
policy scope fails with a 403 from Graph, not a silent no-op.

Deliberately generic — no subcontractor/invite awareness here. The first
caller is the subcontractor-invite flow; a later CO-Request-PDF-emailing
feature is expected to reuse this same function rather than growing its own.
"""
from app.logging_config import get_logger
from app.microsoft import graph_app_client

logger = get_logger(__name__)


def send_mail(from_mailbox: str, to_address: str, subject: str, html_content: str,
              cc_address: str | None = None, save_to_sent: bool = True) -> None:
    """Send an HTML email via Graph /users/{from_mailbox}/sendMail (app-only).

    `from_mailbox` is required, not defaulted — every caller makes an explicit
    choice of sending identity rather than silently going out as some shared
    default. `cc_address` is optional (e.g. the PM who triggered a
    subcontractor invite gets CC'd for their own record, without being the
    send identity). Raises on failure — callers decide how to handle a failed
    send (e.g. surface an error to the admin who triggered it); this function
    does not swallow or retry beyond graph_post's own transient-error/401-
    refresh retries.
    """
    message = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html_content},
        "toRecipients": [{"emailAddress": {"address": to_address}}],
    }
    if cc_address:
        message["ccRecipients"] = [{"emailAddress": {"address": cc_address}}]
    body = {
        "message": message,
        "saveToSentItems": "true" if save_to_sent else "false",
    }
    graph_app_client.graph_post(f"/users/{from_mailbox}/sendMail", json_body=body)
    logger.info("mail_sent", from_mailbox=from_mailbox, to=to_address, cc=cc_address, subject=subject)
