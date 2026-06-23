"""Turn a saved .eml file into the same payload shape the live mail poll lands.

Lets us land a forwarded order email as a RawSourceRecord (and ingest it) without
Microsoft Graph — used by scripts/load_drexel_fixture.py and the parser tests so
the order pipeline is exercisable before the Azure app-only consent is granted.
The payload keys mirror app/lake/ingest/m365_mail._normalize.
"""
import email
from email import policy
from email.utils import parsedate_to_datetime


def _addr_list(value):
    out = []
    for raw in (value or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        name, addr = email.utils.parseaddr(raw)
        out.append({"name": name, "address": (addr or "").lower()})
    return out


def _best_body(msg):
    """Return (content, content_type) preferring HTML (matches Graph), else text."""
    html_part = text_part = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html" and html_part is None:
                html_part = part
            elif ctype == "text/plain" and text_part is None:
                text_part = part
    else:
        if msg.get_content_type() == "text/html":
            html_part = msg
        else:
            text_part = msg
    if html_part is not None:
        return html_part.get_content(), "html"
    if text_part is not None:
        return text_part.get_content(), "text"
    return "", "text"


def eml_to_payload(path):
    """Parse an .eml file into a RawSourceRecord email payload dict."""
    with open(path, "rb") as fh:
        msg = email.message_from_binary_file(fh, policy=policy.default)

    body, content_type = _best_body(msg)

    def _iso(header):
        try:
            dt = parsedate_to_datetime(msg.get(header))
            return dt.isoformat() if dt else None
        except (TypeError, ValueError):
            return None

    from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
    return {
        "external_id": msg.get("Message-ID") or path,
        "subject": msg.get("Subject", "") or "",
        "from": {"name": from_name, "address": (from_addr or "").lower()},
        "to": _addr_list(msg.get("To", "")),
        "cc": _addr_list(msg.get("Cc", "")),
        "received_at": _iso("Date"),
        "sent_at": _iso("Date"),
        "conversation_id": msg.get("Thread-Index"),
        "internet_message_id": msg.get("Message-ID"),
        "preview": "",
        "body_content_type": content_type,
        "body": body,
        "has_attachments": False,
    }
