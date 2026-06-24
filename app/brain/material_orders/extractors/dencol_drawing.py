"""Outbound CAD drawing PDF — qty callouts embedded in a detail sheet.

The "we placed it" half of a Dencol order: David sends Dencol a drawing whose part
marks carry quantity callouts ("Qty (10) - p1000  1/2\" Plate"). The geometry
scrambles the thickness into a stacked fraction — numerator then denominator —
which poppler renders as "3 4" (spaced) and pypdf as "34" (concatenated), so the
regex tolerates either. This is a best-effort deterministic pass — when it can't
recover anything it returns None so the LLM extractor (which reads the PDF natively)
takes over. event_type='placed'.
"""
import re

from app.brain.material_orders import parser
from app.brain.material_orders.extractors import base

NAME = "dencol_drawing"

# "Qty (10) - p1000  1 2 " Plate" / "Qty (10) -p1000 12" Plate" — the thickness is a
# single-digit numerator + single-digit denominator (3/4, 1/2, 3/8, 1/4), with the
# split between them optional (poppler spaces it, pypdf concatenates it).
_CALLOUT_RE = re.compile(
    r"Qty\s*\(\s*(\d+)\s*\)\s*-?\s*([A-Za-z]+\d+)\s+(\d)\s*(\d)\s*\"?\s*"
    r"(Plate|Angle|Tube|Sheet|Bar|Flat|Channel)",
    re.IGNORECASE,
)


def _callouts(record):
    """Recovered (qty, mark, thickness, material) callouts across all attachments."""
    items = []
    seen = set()
    for att in base.attachments(record):
        stream = re.sub(r"\s+", " ", base.raw_text(att))
        for m in _CALLOUT_RE.finditer(stream):
            qty, mark, num, den, material = m.groups()
            if mark.lower() in seen:
                continue
            seen.add(mark.lower())
            thickness = f"{num}/{den}\""
            material = material.title()
            items.append({
                "quantity": float(qty),
                "description": f"{mark} — {thickness} {material}",
                "profile": mark,
                "gauge": None,
                "finish": None,
                "dimension": thickness,
                "unit_price": None,
                "extended_price": None,
                "raw_line": f"Qty ({qty}) - {mark} {thickness} {material}"[:512],
                "line_index": len(items),
            })
    return items


def matches(record):
    return bool(base.attachments(record)) and bool(_callouts(record))


def extract(record):
    lines = _callouts(record)
    if not lines:
        return None
    header = parser.extract_header(record.payload or {})
    return base.order(header, event_type="placed", lines=lines)
