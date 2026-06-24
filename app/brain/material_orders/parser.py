"""Shared parsing helpers for supplier order emails.

The per-shape logic lives in extractors/ (drexel_inline, dencol_confirm,
dencol_drawing, llm); this module holds what they share: HTML→text, supplier
detection, the forwarded-chain orderer parse, and the inline "Qty (n)" body-line
parse. `extract_header(payload)` returns the email-derived fields every extractor
needs (supplier, PO, job/release, orderer); the PDF-shape extractors add their own
line items on top.

`parse_order_email` is the back-compat entry point (header + inline body lines);
extractors/drexel_inline wraps it. Best-effort: `description`/`raw_line` are
authoritative, parsed sub-fields are conveniences and may be None.
"""
import html
import re
from datetime import datetime

from dateutil import parser as _dateutil_parser

from app.logging_config import get_logger

logger = get_logger(__name__)

# Known supplier email domains -> display name. Extend as new suppliers appear.
KNOWN_SUPPLIERS = {
    "drexelsupply.com": "Drexel Supply",
    "dencol.com": "Dencol",
}
SUPPLIER_DOMAINS = set(KNOWN_SUPPLIERS)

_PO_RE = re.compile(r"PO#?\s*[:\-]?\s*(\d{2,5}-\d{2,5})", re.IGNORECASE)
_JOB_RELEASE_RE = re.compile(r"\b(\d{2,5})-(\d{2,5})\b")
# "Qty (45) 1.5C 18Ga. Galvanized Decking @ 48"" — paren optional, qty then desc.
_QTY_LINE_RE = re.compile(r"Qty\.?\s*\(?\s*(\d+)\s*\)?\s*[:\-]?\s*(.+)", re.IGNORECASE)
_CONTACT_TMPL = r'([A-Z][\w.\'-]+(?:\s+[A-Z][\w.\'-]+)*)\s*<\s*([\w.\-+]+@{domain})\s*>'

# Forwarded-chain sender blocks. The orderer is the *innermost internal* sender —
# the MHMW person who actually placed the order — not a forwarder above it and not
# the supplier who replied below it. Two header formats appear:
#   Outlook reply : "From: David Servold <DServold@mhmw.com>" + "Sent:"/"Date:"
#   Outlook quote : 'From "David Servold" <DServold@mhmw.com>' + "Date 4/23/2026"
#                   (the "------ Original Message ------" block — no colons)
_FROM_COLON_RE = re.compile(r"^\s*From:\s*(.+?)\s*$", re.IGNORECASE)
_FROM_NOCOLON_RE = re.compile(r"^\s*From\s+(.+<[^>]*@[^>]*>.*)$", re.IGNORECASE)
_DATE_COLON_RE = re.compile(r"^\s*(?:Sent|Date):\s*(.+?)\s*$", re.IGNORECASE)
_DATE_NOCOLON_RE = re.compile(r"^\s*Date\s+(.+?)\s*$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.\-+]+@[\w.\-]+")

_PROFILE_RE = re.compile(r"\b(\d+(?:\.\d+)?[A-Z]{1,2})\b")          # 1.5C
_GAUGE_RE = re.compile(r"\b(\d{1,2})\s*ga\b\.?", re.IGNORECASE)      # 18Ga / 18 ga
_DIM_RE = re.compile(r"@\s*(\d+(?:\.\d+)?\s*(?:\"|''|in\b|'|ft\b)?)")  # @ 48"
_FINISH_WORDS = [
    "galvanized", "galv", "stainless", "painted", "primed", "prime",
    "black", "powder", "hot-dip", "hot dip",
]


def _html_to_text(body, content_type):
    """Collapse an HTML or text email body into newline-separated plain text."""
    if not body:
        return ""
    text = body
    # Strip tags for HTML bodies. When the content type is explicitly text/plain we
    # must NOT — a plain-text forward can contain a real '<addr@host>' that the tag
    # regex would otherwise eat (dropping the sender address we parse the orderer from).
    ctype = (content_type or "").lower()
    looks_html = "<" in text and ">" in text
    if ctype == "html" or (ctype not in ("text", "plain") and looks_html):
        text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
        text = re.sub(r"(?i)</\s*(p|div|tr|li|h[1-6])\s*>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")  # &nbsp; -> normal space
    # Normalize whitespace per line, drop blank lines.
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _detect_supplier(text):
    """Return (supplier_name, contact_str) for the first known supplier domain seen."""
    for domain, name in KNOWN_SUPPLIERS.items():
        if domain.lower() in text.lower():
            contact = None
            m = re.search(_CONTACT_TMPL.format(domain=re.escape(domain)), text, re.IGNORECASE)
            if m:
                contact = f"{m.group(1).strip()} <{m.group(2).strip().lower()}>"
            else:
                m2 = re.search(rf"[\w.\-+]+@{re.escape(domain)}", text, re.IGNORECASE)
                if m2:
                    contact = m2.group(0).lower()
            return name, contact
    return None, None


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _parse_email_date(value):
    """Parse a free-form forwarded-header date ('Sent:'/'Date:' value) to a datetime."""
    if not value:
        return None
    # Gmail renders "Mon, Jun 15, 2026 at 8:31 AM" — drop the " at " connector.
    cleaned = re.sub(r"\s+at\s+", " ", value, flags=re.IGNORECASE).strip()
    try:
        return _dateutil_parser.parse(cleaned, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None


def _name_email(raw_from):
    """A 'From' line's content -> (name, email). email = first @ token in the line."""
    em = _EMAIL_RE.search(raw_from)
    email = em.group(0).lower() if em else None
    name = raw_from.split("<", 1)[0].strip().strip('"').strip() or None
    return name, email


def _is_supplier_email(email):
    return bool(email) and email.split("@")[-1].lower() in SUPPLIER_DOMAINS


def _parse_orderer(text):
    """Extract (name, email, ordered_dt) of the order's original *internal* sender.

    Walks every forwarded "From" block (both the colon "From:" reply format and the
    no-colon 'From "Name" <addr>' Outlook quote format). The orderer is the deepest
    block whose address is an MHMW/internal one — never a supplier who replied in
    the thread, and never a forwarder above the original. ordered_dt is that block's
    Sent/Date; if no internal block exists, name/email are None and the date falls
    back to the deepest block (caller then falls back to the envelope).
    """
    lines = text.splitlines()
    blocks = []  # list of {name, email, date}
    for i, line in enumerate(lines):
        m = _FROM_COLON_RE.match(line) or _FROM_NOCOLON_RE.match(line)
        if not m:
            continue
        name, email = _name_email(m.group(1).strip())
        date = None
        for ln in lines[i + 1: i + 7]:
            dm = _DATE_COLON_RE.match(ln) or _DATE_NOCOLON_RE.match(ln)
            if dm:
                date = _parse_email_date(dm.group(1))
                break
        blocks.append({"name": name, "email": email, "date": date})

    if not blocks:
        return None, None, None

    # A block is disqualified only when its address is a supplier domain (the
    # supplier who replied). A name-only block (Outlook dropped the address) is an
    # outbound MHMW sender — keep it eligible so a forward with no inner address
    # still yields the orderer's name.
    internal = [b for b in blocks if not _is_supplier_email(b["email"])]
    chosen = internal[-1] if internal else None
    name = chosen["name"] if chosen else None
    email = chosen["email"] if chosen else None
    date = (chosen and chosen["date"]) or blocks[-1]["date"]
    return name, email, date


def _parse_part(description):
    """Best-effort split of a part description into profile/gauge/finish/dimension."""
    profile = gauge = finish = dimension = None
    m = _PROFILE_RE.search(description)
    if m:
        profile = m.group(1)
    m = _GAUGE_RE.search(description)
    if m:
        gauge = f"{m.group(1)}Ga"
    m = _DIM_RE.search(description)
    if m:
        dimension = re.sub(r"\s+", "", m.group(1))
    low = description.lower()
    for word in _FINISH_WORDS:
        if word in low:
            finish = "Galvanized" if word in ("galv", "galvanized") else word.title()
            break
    return profile, gauge, finish, dimension


def extract_header(payload):
    """Email-derived order fields shared by every extractor.

    {supplier, supplier_contact, po_number, job, release, ordered_by,
    ordered_by_email, ordered_at}. No line items — PDF-shape extractors add their
    own. `haystack` (subject + body text) is returned too so callers can reuse it.
    """
    subject = (payload.get("subject") or "").strip()
    text = _html_to_text(payload.get("body"), payload.get("body_content_type"))
    haystack = f"{subject}\n{text}"

    po_number = None
    m = _PO_RE.search(haystack)
    if m:
        po_number = m.group(1)
    job = release = None
    jr = _JOB_RELEASE_RE.search(po_number or subject or "")
    if jr:
        job = int(jr.group(1))
        release = jr.group(2)

    supplier, supplier_contact = _detect_supplier(haystack)

    ordered_by, ordered_by_email, orderer_dt = _parse_orderer(text)
    ordered_dt = orderer_dt or _parse_dt(payload.get("sent_at")) or _parse_dt(payload.get("received_at"))

    return {
        "supplier": supplier,
        "supplier_contact": supplier_contact,
        "po_number": po_number,
        "job": job,
        "release": release,
        "ordered_by": ordered_by,
        "ordered_by_email": ordered_by_email,
        "ordered_at": ordered_dt.date() if ordered_dt else None,
        "_haystack": haystack,
    }


def parse_inline_lines(haystack):
    """Every "Qty (n) <desc>" order line typed into an email body."""
    lines = []
    for raw_line in haystack.splitlines():
        lm = _QTY_LINE_RE.search(raw_line)
        if not lm:
            continue
        qty = float(lm.group(1))
        description = lm.group(2).strip().rstrip(".")
        profile, gauge, finish, dimension = _parse_part(description)
        lines.append({
            "quantity": qty,
            "description": description,
            "profile": profile,
            "gauge": gauge,
            "finish": finish,
            "dimension": dimension,
            "unit_price": None,
            "extended_price": None,
            "raw_line": raw_line.strip()[:512],
            "line_index": len(lines),
        })
    return lines


def parse_order_email(payload):
    """RawSourceRecord email payload -> parsed inline order dict, or None.

    Header fields + inline body "Qty (n)" lines (the Drexel shape). Returns None
    when the message is not a recognizable order (no PO and no order lines).
    Back-compat entry point; extractors/drexel_inline wraps it.
    """
    if not payload:
        return None
    header = extract_header(payload)
    lines = parse_inline_lines(header.pop("_haystack"))
    if not lines and not header.get("po_number"):
        return None
    return {**header, "event_type": "placed", "supplier_order_no": None, "lines": lines}
