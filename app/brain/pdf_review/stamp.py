"""Bake a small 'BB-N/X' page anchor into downloaded Procore drawing PDFs.

Each page of a pulled drawing set gets a plain-black 'BB-N/X' stamp in its visual
upper-left corner, where N is the 1-based page position and X is the total page count.
The review model reads this stamp to return a machine-anchor `page` per finding so the
viewer can jump straight to the right sheet. Stamping is best-effort: any failure falls
back to the original bytes so it can never block a download.
"""
import io

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from app.logging_config import get_logger

logger = get_logger(__name__)


def _overlay(width: float, height: float, text: str):
    """Return a single-page overlay PdfReader page carrying `text` in the upper-left."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0, 0, 0)
    # PDF origin is bottom-left; upper-left is y near the top of the page.
    c.drawString(10, height - 10 - 9, text)
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def stamp_pdf_pages(pdf_bytes: bytes, *, prefix: str = "BB") -> bytes:
    """Return pdf_bytes with 'BB-N/X' baked into the upper-left of every page."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        total = len(reader.pages)
        writer = PdfWriter()
        for i, page in enumerate(reader.pages, start=1):
            try:
                page.transfer_rotation_to_content()
            except Exception:
                pass
            box = page.mediabox
            w = float(box.width)
            h = float(box.height)
            overlay_page = _overlay(w, h, f"{prefix}-{i}/{total}")
            page.merge_page(overlay_page)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        logger.warning("bb_stamp_failed", exc_info=True)
        return pdf_bytes
