"""Tests for the BB-N/X page stamp baked into pulled Procore drawing PDFs."""
import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.brain.pdf_review.stamp import stamp_pdf_pages


def _two_page_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.drawString(100, 700, "Sheet F1")
    c.showPage()
    c.drawString(100, 700, "Sheet F2")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_stamp_bakes_bb_anchor_on_every_page():
    stamped = stamp_pdf_pages(_two_page_pdf())

    reader = PdfReader(io.BytesIO(stamped))
    assert len(reader.pages) == 2

    assert "BB-1/2" in reader.pages[0].extract_text()
    assert "BB-2/2" in reader.pages[1].extract_text()


def test_malformed_bytes_returns_input_unchanged():
    garbage = b"not a pdf"
    assert stamp_pdf_pages(garbage) == garbage
