"""
@milehigh-header
schema_version: 1
purpose: Register Carlito (the metric-compatible stand-in for Calibri) with reportlab so
  server-rendered PDFs are set in the same face as the app, degrading to Helvetica if the
  font files are missing.
exports:
  FONT / FONT_BOLD / FONT_ITALIC -> reportlab font names, resolved on first use
  register_pdf_fonts() -> (regular, bold, italic) tuple
imports_from: [pathlib, reportlab.pdfbase]
imported_by: [app.brain.lookahead.export_pdf]
invariants:
  - Never raises. A missing or unreadable .ttf falls back to the Standard-14 Helvetica
    family, so a PDF still renders.
  - Registration happens once per process; reportlab's font registry is global.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.logging_config import get_logger

logger = get_logger(__name__)

# The client asked for Calibri, which is Microsoft-licensed and cannot be embedded in a
# PDF we ship. Carlito is its metric-compatible open twin (same advance widths, same
# shapes, OFL), so a print set in Carlito and one set in Calibri lay out line-for-line
# identically.
#
# The .ttf files are generated from the @fontsource WOFFs by scripts/build_pdf_fonts.py
# and live under the frontend's public/ because the browser-side Job Log export fetches
# them over HTTP from there. They are one set of binaries, not two: duplicating them into
# a backend asset directory would mean two copies to keep in step across a version bump.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_FONT_DIRS = (
    _REPO_ROOT / "frontend" / "public" / "fonts",
    # A deploy that ships only the built frontend still has them here — Vite copies
    # public/ into dist/ verbatim.
    _REPO_ROOT / "frontend" / "dist" / "fonts",
)

_FACES = (
    ("Carlito", "carlito-400.ttf"),
    ("Carlito-Bold", "carlito-700.ttf"),
    ("Carlito-Italic", "carlito-400-italic.ttf"),
)

_HELVETICA = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique")
_CARLITO = ("Carlito", "Carlito-Bold", "Carlito-Italic")

_resolved: tuple[str, str, str] | None = None


def _find(filename: str) -> Path | None:
    for directory in _FONT_DIRS:
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def register_pdf_fonts() -> tuple[str, str, str]:
    """Return the (regular, bold, italic) font names to draw with.

    Registers Carlito with reportlab's global font registry on first call and caches the
    outcome. Returns the Helvetica family instead if any face is missing or unreadable —
    a PDF in the wrong typeface beats a 500 on a GC-facing download.
    """
    global _resolved
    if _resolved is not None:
        return _resolved

    try:
        for name, filename in _FACES:
            path = _find(filename)
            if path is None:
                raise FileNotFoundError(filename)
            pdfmetrics.registerFont(TTFont(name, str(path)))
        # Lets reportlab resolve bold/italic from the base name where a caller uses
        # Paragraph markup rather than setFont directly.
        pdfmetrics.registerFontFamily(
            "Carlito", normal="Carlito", bold="Carlito-Bold", italic="Carlito-Italic",
        )
        _resolved = _CARLITO
    except Exception as exc:
        logger.warning(
            "pdf_font_fallback",
            font="Carlito",
            fallback="Helvetica",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        _resolved = _HELVETICA

    return _resolved
