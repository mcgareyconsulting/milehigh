"""Inline-text order: line items typed into the email body as "Qty (n) <desc>".

The original (Drexel Supply) shape — and any supplier who lists parts in the body.
Pure delegation to parser.parse_order_email; event_type is always 'placed' (an
outbound order request).
"""
from app.brain.material_orders import parser

NAME = "drexel_inline"


def matches(record):
    """True when the email body carries inline 'Qty (n)' order lines."""
    header = parser.extract_header(record.payload or {})
    return bool(parser.parse_inline_lines(header.get("_haystack", "")))


def extract(record):
    parsed = parser.parse_order_email(record.payload or {})
    if not parsed or not parsed.get("lines"):
        return None
    return parsed
