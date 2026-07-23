"""Bake a small 'BB-N/X' page anchor into downloaded Procore drawing PDFs.

Each page of a pulled drawing set gets a plain-black 'BB-N/X' stamp in its visual
upper-left corner, where N is the 1-based page position and X is the total page count.
The review model reads this stamp to return a machine-anchor `page` per finding so the
viewer can jump straight to the right sheet. Stamping is best-effort: any failure falls
back to the original bytes so it can never block a download.

The page's own /Rotate is left untouched. Procore renders a document's markups as PDF
annotations whose /Rect lives in the page's unrotated coordinate space; baking the
rotation into the content (pypdf's `transfer_rotation_to_content`) rewrites the content
and the boxes but NOT the annotations, so every markup came out 90 degrees off and
displaced. Instead the stamp itself is rotated to match the page, landing upright in the
visual upper-left of the displayed sheet while every markup stays exactly where Procore
put it.
"""
import io

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from app.logging_config import get_logger

logger = get_logger(__name__)

MARGIN = 10.0
FONT_SIZE = 9.0


def _baseline_origin(rotation: int, x0: float, y0: float, w: float, h: float):
    """Return the PDF-space point where the stamp's baseline starts.

    Viewers rotate the page clockwise by `rotation` before display, so the point that
    ends up in the visual upper-left differs per rotation. `x0`/`y0` are the box origin
    (usually 0,0) and `w`/`h` its unrotated size.
    """
    m, f = MARGIN, FONT_SIZE
    if rotation == 90:
        return x0 + m + f, y0 + m
    if rotation == 180:
        return x0 + w - m, y0 + m + f
    if rotation == 270:
        return x0 + w - m - f, y0 + h - m
    return x0 + m, y0 + h - m - f


def _overlay(page_width: float, page_height: float, origin, rotation: int, text: str):
    """Return a single-page overlay PdfReader page carrying `text`, rotated to match."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.setFont("Helvetica-Bold", FONT_SIZE)
    c.setFillColorRGB(0, 0, 0)
    c.saveState()
    c.translate(origin[0], origin[1])
    # Content rotated by `rotation` in PDF space reads upright once the viewer applies
    # the page's clockwise /Rotate.
    if rotation:
        c.rotate(rotation)
    c.drawString(0, 0, text)
    c.restoreState()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def stamp_pdf_pages(pdf_bytes: bytes, *, prefix: str = "BB") -> bytes:
    """Return pdf_bytes with 'BB-N/X' baked into the visual upper-left of every page."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        total = len(reader.pages)
        writer = PdfWriter()
        for i, page in enumerate(reader.pages, start=1):
            try:
                rotation = int(page.rotation or 0) % 360
            except Exception:
                rotation = 0
            if rotation % 90:
                rotation = 0
            # Viewers clip to the CropBox when there is one, so anchor to it.
            box = page.cropbox if "/CropBox" in page else page.mediabox
            x0, y0 = float(box.left), float(box.bottom)
            w, h = float(box.width), float(box.height)
            origin = _baseline_origin(rotation, x0, y0, w, h)
            overlay_page = _overlay(x0 + w, y0 + h, origin, rotation, f"{prefix}-{i}/{total}")
            page.merge_page(overlay_page)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        logger.warning("bb_stamp_failed", exc_info=True)
        return pdf_bytes
