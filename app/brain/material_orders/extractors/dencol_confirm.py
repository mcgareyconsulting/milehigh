"""Dencol ORDER CONFIRM PDF — a clean priced table the supplier sends back.

Email header fields come from `extract_header` (supplier=Dencol, PO, orderer); the
line items + Dencol's own Order # come from the attached confirm PDF's text. Each
priced row pairs a qty/price line with a description line:

    LASER WORK    2   $30.50 EA   $61.00 ...                 (qty + unit + extended)
    2 PC. 1/2" A36 PL 1 1/2" X 38 1/2" PER DRAWING 351-b1014  (qty + spec + drawing)

The text-extraction engine matters: poppler renders "$30.50 EA $61.00", pypdf
renders "$30.50 $61.00EA $61.00" (EA bound to the extended price), and on hosts
without poppler we run pypdf. So we don't trust dollar *order* — we recover unit
vs extended from the qty×unit=extended invariant, which holds under either engine.
event_type='confirmed' — this is the supplier acknowledging the order.
"""
import re

from app.brain.material_orders import parser
from app.brain.material_orders.extractors import base

NAME = "dencol_confirm"

# "2 PC. 1/2\" A36 PL 1 1/2\" X 38 1/2\" PER DRAWING 351-b1014"
_DESC_RE = re.compile(r"(\d+)\s*PC\.\s*(.+?)\s+PER\s+DRAWING\s+([^\s,;]+)", re.IGNORECASE)
_DOLLAR_RE = re.compile(r"\$\s*([\d,]+\.\d{2})")
# pypdf dissociates the "Order #:" label from its value (the customer # M11050 can
# even sit between), so allow a gap and require 6-8 digits — Dencol order numbers
# are 7 digits, which skips the 5-digit customer fragment.
_ORDER_NO_RE = re.compile(r"Order\s*#\s*:?[\s\S]{0,80}?(\d{6,8})", re.IGNORECASE)


def _money(value):
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _prices_for(qty, lines, i):
    """Recover (unit, extended) for a row from the dollar amounts near its
    description line, using unit×qty == extended (engine-independent)."""
    window = " ".join(lines[max(0, i - 2):i + 1])
    dollars = [_money(d) for d in _DOLLAR_RE.findall(window)]
    dollars = [d for d in dollars if d is not None]
    for unit in sorted({d for d in dollars if d > 0}):
        extended = round(unit * qty, 2)
        if extended in dollars:
            return unit, extended
    return None, None


def _parse_table(text):
    """Pull priced line items + the supplier Order # from confirm-PDF text."""
    lines = text.splitlines()
    items = []
    for i, line in enumerate(lines):
        m = _DESC_RE.search(line)
        if not m:
            continue
        qty = float(m.group(1))
        spec = m.group(2).strip()
        drawing = m.group(3).strip().rstrip(".,;")
        description = f"{int(qty)} PC. {spec} PER DRAWING {drawing}"

        unit_price, extended_price = _prices_for(qty, lines, i)
        profile, gauge, finish, dimension = parser._parse_part(spec)
        items.append({
            "quantity": qty,
            "description": description,
            "profile": profile,
            "gauge": gauge,
            "finish": finish,
            "dimension": dimension,
            "unit_price": unit_price,
            "extended_price": extended_price,
            "raw_line": description[:512],
            "line_index": len(items),
        })

    mo = _ORDER_NO_RE.search(text)
    return items, (mo.group(1) if mo else None)


def _confirm_text(record):
    """First attachment whose text looks like a Dencol confirm table, else ''."""
    for att in base.pdf_attachments(record):
        text = att.get("text") or ""
        if _DESC_RE.search(text) and _DOLLAR_RE.search(text):
            return text
    return ""


def matches(record):
    return bool(_confirm_text(record))


def extract(record):
    text = _confirm_text(record)
    if not text:
        return None
    lines, order_no = _parse_table(text)
    if not lines:
        return None
    header = parser.extract_header(record.payload or {})
    return base.order(header, event_type="confirmed", lines=lines, supplier_order_no=order_no)
