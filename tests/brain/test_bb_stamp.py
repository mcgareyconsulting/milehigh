"""Tests for the BB-N/X page stamp baked into pulled Procore drawing PDFs."""
import io
import math

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText
from pypdf.generic import NameObject, NumberObject
from reportlab.pdfgen import canvas

from app.brain.pdf_review.stamp import stamp_pdf_pages

PAGE_W, PAGE_H = 612.0, 792.0
MARKUP_RECT = (50, 700, 250, 740)


def _two_page_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.drawString(100, 700, "Sheet F1")
    c.showPage()
    c.drawString(100, 700, "Sheet F2")
    c.showPage()
    c.save()
    return buf.getvalue()


def _rotated_pdf_with_markup(rotation: int) -> bytes:
    """One page carrying /Rotate plus an annotation, like a Procore markup download."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.drawString(100, 700, "Sheet F1")
    c.showPage()
    c.save()

    page = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
    page[NameObject("/Rotate")] = NumberObject(rotation)
    writer = PdfWriter()
    writer.add_page(page)
    writer.add_annotation(
        page_number=0, annotation=FreeText(text="MARKUP", rect=MARKUP_RECT),
    )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _annotation_rects(page):
    return [[float(v) for v in a.get_object()["/Rect"]] for a in page.get("/Annots", [])]


def _stamp_matrix(pdf_bytes: bytes):
    """Return the stamp's (cos, sin, x, y) in PDF space, composing cm with tm."""
    found = {}

    def visit(text, cm, tm, font, size):
        if "BB-" in text and not found:
            a, b, c, d, e, f = tm
            A, B, C, D, E, F = cm
            found['m'] = (a * A + b * C, a * B + b * D,
                          e * A + f * C + E, e * B + f * D + F)

    PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text(visitor_text=visit)
    return found.get('m')


def _to_display(rotation, x, y):
    """Map a PDF-space point to the displayed page (viewers rotate clockwise)."""
    if rotation == 90:
        return y, PAGE_W - x
    if rotation == 180:
        return PAGE_W - x, PAGE_H - y
    if rotation == 270:
        return PAGE_H - y, x
    return x, y


def test_stamp_bakes_bb_anchor_on_every_page():
    stamped = stamp_pdf_pages(_two_page_pdf())

    reader = PdfReader(io.BytesIO(stamped))
    assert len(reader.pages) == 2

    assert "BB-1/2" in reader.pages[0].extract_text()
    assert "BB-2/2" in reader.pages[1].extract_text()


def test_malformed_bytes_returns_input_unchanged():
    garbage = b"not a pdf"
    assert stamp_pdf_pages(garbage) == garbage


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_stamping_leaves_page_rotation_and_markups_alone(rotation):
    """Regression: baking the rotation into the content left Procore's markup
    annotations behind in the old coordinate frame, so every markup rendered 90
    degrees off and displaced."""
    stamped = stamp_pdf_pages(_rotated_pdf_with_markup(rotation))
    page = PdfReader(io.BytesIO(stamped)).pages[0]

    assert page.rotation == rotation
    assert [float(v) for v in page.mediabox] == [0, 0, PAGE_W, PAGE_H]
    assert _annotation_rects(page) == [list(MARKUP_RECT)]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_stamp_lands_upright_in_the_visual_upper_left(rotation):
    stamped = stamp_pdf_pages(_rotated_pdf_with_markup(rotation))
    cos, sin, x, y = _stamp_matrix(stamped)

    # The stamp is rotated with the page, so it reads upright once displayed.
    assert (round(cos, 3), round(sin, 3)) == (
        round(math.cos(math.radians(rotation)), 3),
        round(math.sin(math.radians(rotation)), 3),
    )

    display_h = PAGE_W if rotation in (90, 270) else PAGE_H
    dx, dy = _to_display(rotation, x, y)
    assert dx == pytest.approx(10.0)
    assert dy == pytest.approx(display_h - 19.0)
