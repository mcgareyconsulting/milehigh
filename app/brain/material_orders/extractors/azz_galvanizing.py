"""AZZ Galvanizing status notification — the galvanizer telling us where our steel is.

AZZ (azz.com) coats our fabricated steel and emails a status notification each time
the job's state changes ("Received", "In Process", "Ready to Ship", "Shipped"). The
body is a labeled block:

    AZZ Job        26070025          (the galvanizer's own job # — our upsert key)
    Customer PO    480-913           (our job-release — parsed by extract_header)
    Description    ANGLE             (what's being galvanized; no quantity)

There are no itemized parts or prices — it's a single status row per galv job. The
subject/body carry the status ("... has changed: Ready to Ship"); we map it to the
shipping-planning lifecycle (only a 'Shipped' notification is 'complete' — the steel
has left the galvanizer; everything earlier is still 'planning', i.e. out at galv).
event_type='status'; order_kind='galvanizing'. The service upserts ONE row per AZZ
Job # so successive notifications advance the same row rather than piling up.
"""
import re

from app.brain.material_orders import parser
from app.brain.material_orders.extractors import base

NAME = "azz_galvanizing"

_SUPPLIER_DOMAIN = "azz.com"
_JOB_NO_RE = re.compile(r"AZZ\s*Job\b", re.IGNORECASE)
# The authoritative job-release link for an AZZ notification: the six-digit
# "Customer PO xxx-yyy" in the body. Anchored on the "Customer PO" label (not any
# stray PO-like token) so it's deterministic — job=xxx, release=yyy. AZZ renders the
# block as an HTML table / plain-text label pairs, so allow the label and value to be
# separated by whitespace or a stray tag-gap the html-strip left behind.
_CUSTOMER_PO_RE = re.compile(r"Customer\s*PO\b[^\d]{0,20}(\d{3})-(\d{3})", re.IGNORECASE)
# Status is announced two ways: in the body ("order status has changed: <status>.")
# and as the trailing comma-segment of the subject ("..., Ready to Ship"). Stop the
# body capture at the sentence end so trailing boilerplate isn't pulled into it.
_STATUS_BODY_RE = re.compile(r"status\s+has\s+changed:\s*([^.\n]+)", re.IGNORECASE)
# "Shipped" means the galvanizer sent our steel back — the only status that closes
# the shipping-planning item; Received / In Process / Ready to Ship are still out.
_COMPLETE_RE = re.compile(r"\b(shipped|delivered|picked\s*up|complete)\b", re.IGNORECASE)


def _labeled_value(lines, label):
    """Value of a labeled block field: the first non-empty line after the label line."""
    for i, line in enumerate(lines):
        if line.strip().lower() == label.lower():
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    return nxt.strip()
            return None
    return None


def _customer_po(haystack, record):
    """The 'Customer PO xxx-yyy' six-digit job-release, from the body then any PDF.

    Returns (po_number, job, release) or (None, None, None). AZZ puts the PO inline
    today; the PDF fallback (deterministic text extraction, no LLM) covers the case
    where a future notification carries the block only as an attached PDF. An inline
    *image*-only PO is the sole shape this can't recover — it would need OCR.
    """
    m = _CUSTOMER_PO_RE.search(haystack)
    if not m:
        for att in base.pdf_attachments(record):
            m = _CUSTOMER_PO_RE.search(att.get("text") or "")
            if m:
                break
    if not m:
        return None, None, None
    return f"{m.group(1)}-{m.group(2)}", int(m.group(1)), m.group(2)


def _status(subject, lines):
    m = _STATUS_BODY_RE.search("\n".join(lines))
    if m:
        return m.group(1).strip().rstrip(".")
    if "," in (subject or ""):
        return subject.rsplit(",", 1)[-1].strip()
    return None


def matches(record):
    header = parser.extract_header(record.payload or {})
    haystack = header.get("_haystack", "")
    low = haystack.lower()
    return _SUPPLIER_DOMAIN in low and (
        bool(_JOB_NO_RE.search(haystack)) or "order status has changed" in low
    )


def extract(record):
    header = parser.extract_header(record.payload or {})
    haystack = header.get("_haystack", "")
    lines = haystack.splitlines()

    supplier_order_no = _labeled_value(lines, "AZZ Job")
    material = _labeled_value(lines, "Description")
    subject = (record.payload or {}).get("subject") or ""
    status = _status(subject, lines)

    # Authoritative job-release: the anchored "Customer PO xxx-yyy" (body then PDF),
    # overriding whatever loose PO token the shared header parser may have grabbed.
    po_number, job, release = _customer_po(haystack, record)
    if po_number:
        header["po_number"], header["job"], header["release"] = po_number, job, release

    # The shared contact parser mangles AZZ's "addr <addr>" self-reference into a
    # "azz.com <...>" display string; the plain notification address reads cleaner.
    m = re.search(r"[\w.\-+]+@azz\.com", haystack, re.IGNORECASE)
    if m:
        header["supplier_contact"] = m.group(0).lower()

    shipping_status = "complete" if status and _COMPLETE_RE.search(status) else "planning"
    description = f"Galvanizing: {material}" if material else "Galvanizing order"
    raw_line = " — ".join(
        p for p in (
            f"AZZ Job {supplier_order_no}" if supplier_order_no else None,
            status,
        ) if p
    ) or description

    profile, gauge, finish, dimension = parser._parse_part(material or "")
    line = {
        "quantity": None,
        "description": description,
        "profile": profile,
        "gauge": gauge,
        "finish": finish or "Galvanized",
        "dimension": dimension,
        "unit_price": None,
        "extended_price": None,
        "raw_line": raw_line[:512],
        "line_index": 0,
    }
    return base.order(
        header,
        event_type="status",
        lines=[line],
        supplier_order_no=supplier_order_no,
        order_kind="galvanizing",
        shipping_status=shipping_status,
    )
