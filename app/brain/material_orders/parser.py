"""Parse supplier order emails into structured order line items.

Input is a RawSourceRecord email payload (see app/lake/ingest/m365_mail._normalize):
{subject, from, to, body, body_content_type, received_at, sent_at, ...}. The
emails we care about are forwarded supplier orders, e.g.:

    To: Nick Hagenlock <nick@drexelsupply.com>
    Subject: 580-659 Blue Room House One Decking Order
    Please use PO# 580-659 Stair Decking
    Qty (45) 1.5C 18Ga. Galvanized Decking @ 48"

parse_order_email returns a dict {supplier, supplier_contact, po_number, job,
release, ordered_at, lines: [{quantity, description, profile, gauge, finish,
dimension, raw_line, line_index}]} or None when the message isn't a recognizable
order (no PO + no order lines). Best-effort: `description`/`raw_line` are
authoritative; the parsed sub-fields are conveniences and may be None.
"""
import html
import re
from datetime import datetime

# Known supplier email domains -> display name. Extend as new suppliers appear.
KNOWN_SUPPLIERS = {
    "drexelsupply.com": "Drexel Supply",
    "dencol.com": "Dencol",
}

_PO_RE = re.compile(r"PO#?\s*[:\-]?\s*(\d{2,5}-\d{2,5})", re.IGNORECASE)
_JOB_RELEASE_RE = re.compile(r"\b(\d{2,5})-(\d{2,5})\b")
# "Qty (45) 1.5C 18Ga. Galvanized Decking @ 48"" — paren optional, qty then desc.
_QTY_LINE_RE = re.compile(r"Qty\.?\s*\(?\s*(\d+)\s*\)?\s*[:\-]?\s*(.+)", re.IGNORECASE)
_CONTACT_TMPL = r'([A-Z][\w.\'-]+(?:\s+[A-Z][\w.\'-]+)*)\s*<\s*([\w.\-+]+@{domain})\s*>'

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
    if (content_type or "").lower() == "html" or "<" in text and ">" in text:
        text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
        text = re.sub(r"(?i)</\s*(p|div|tr|li|h[1-6])\s*>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")  # &nbsp; -> normal space
    # Normalize whitespace per line, drop blank lines.
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
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


def parse_order_email(payload):
    """RawSourceRecord email payload -> parsed order dict, or None if not an order."""
    if not payload:
        return None

    subject = (payload.get("subject") or "").strip()
    text = _html_to_text(payload.get("body"), payload.get("body_content_type"))
    haystack = f"{subject}\n{text}"

    # PO number (preferred) then a bare job-release token in the subject.
    po_number = None
    m = _PO_RE.search(haystack)
    if m:
        po_number = m.group(1)
    job = release = None
    jr = _JOB_RELEASE_RE.search(po_number or subject or "")
    if jr:
        job = int(jr.group(1))
        release = jr.group(2)

    # Order lines: every "Qty (n) <desc>" we can find.
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
            "raw_line": raw_line.strip()[:512],
            "line_index": len(lines),
        })

    # Not an order if we found neither a PO nor any order lines.
    if not lines and not po_number:
        return None

    supplier, supplier_contact = _detect_supplier(haystack)
    ordered_dt = _parse_dt(payload.get("sent_at")) or _parse_dt(payload.get("received_at"))

    return {
        "supplier": supplier,
        "supplier_contact": supplier_contact,
        "po_number": po_number,
        "job": job,
        "release": release,
        "ordered_at": ordered_dt.date() if ordered_dt else None,
        "lines": lines,
    }
