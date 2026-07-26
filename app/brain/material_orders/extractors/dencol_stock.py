"""DenCol stock materials order — a shop restock not tied to any release.

The shop periodically restocks common material from DenCol under a "Stock <date>"
PO (e.g. "PO# Stock 7/7/26"), with no job/release and no itemized parts quoted in
the forwarded chain — it just needs to be tracked for shipping planning until it's
picked up. DenCol replies "this order is complete and ready for pick up".

This is deliberately LAST in the deterministic chain and gated on the "Stock <date>"
PO so it never swallows a normal DenCol order (those route to dencol_confirm /
dencol_drawing via their PDF, which run first). One summary row, no parts:
event_type='status', order_kind='stock', shipping_status planning→complete.
"""
import re

from app.brain.material_orders import parser
from app.brain.material_orders.extractors import base

NAME = "dencol_stock"

_SUPPLIER_DOMAIN = "dencol.com"
# "PO# Stock 7/7/26" — the stock marker + its date, the signal that distinguishes a
# restock from a job order (which carries a NNN-NNN PO instead).
_STOCK_PO_RE = re.compile(r"PO#?\s*[:\-]?\s*(Stock\s+[\d/.\-]+)", re.IGNORECASE)
_PICKED_UP_RE = re.compile(r"\b(picked\s*up|shipped|delivered|received)\b", re.IGNORECASE)


def _stock_po(haystack):
    m = _STOCK_PO_RE.search(haystack)
    return m.group(1).strip() if m else None


def matches(record):
    header = parser.extract_header(record.payload or {})
    haystack = header.get("_haystack", "")
    return _SUPPLIER_DOMAIN in haystack.lower() and bool(_stock_po(haystack))


def extract(record):
    header = parser.extract_header(record.payload or {})
    haystack = header.pop("_haystack", "")
    po_number = _stock_po(haystack)

    # A stock restock is never tied to a release — drop any job/release the shared
    # header may have picked up from stray digits, and use the Stock PO instead.
    header["job"] = None
    header["release"] = None
    header["po_number"] = po_number

    low = haystack.lower()
    shipping_status = "complete" if _PICKED_UP_RE.search(low) else "planning"
    ready = "ready for pick up" in low or "ready for pickup" in low
    # ready_at = the date DenCol (@dencol.com) said it was ready for pickup — the
    # supplier's reply date in the forwarded chain. ordered_at (Luis's order date)
    # is already set by the shared header from the innermost internal sender.
    if ready:
        header["ready_at"] = parser.supplier_reply_date(haystack)
    description = f"Stock materials order ({po_number})" if po_number else "Stock materials order"
    raw_line = "DenCol stock order — ready for pickup" if ready else "DenCol stock order"

    line = {
        "quantity": None,
        "description": description,
        "profile": None,
        "gauge": None,
        "finish": None,
        "dimension": None,
        "unit_price": None,
        "extended_price": None,
        "raw_line": raw_line[:512],
        "line_index": 0,
    }
    return base.order(
        header,
        event_type="status",
        lines=[line],
        order_kind="stock",
        shipping_status=shipping_status,
    )
