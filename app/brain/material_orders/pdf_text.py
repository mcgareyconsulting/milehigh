"""Extract plain text from PDF attachment bytes.

Supplier orders arrive as two PDF shapes (see extractors/): a clean tabular
"ORDER CONFIRM" and a scrambled CAD drawing. `pdftotext -layout` (poppler) keeps
table columns aligned and is what the Dencol-confirm extractor wants; `-raw`
preserves drawing qty-callouts in reading order. Poppler isn't guaranteed on every
host (e.g. Render), so we fall back to pypdf, which is a pure-Python dependency.

extract_text(data) -> str returns "" on any failure — callers treat empty text as
"no deterministic signal" and let the LLM extractor read the original PDF instead.
"""
import shutil
import subprocess

from app.logging_config import get_logger

logger = get_logger(__name__)

_PDFTOTEXT = shutil.which("pdftotext")


def _pdftotext(data: bytes, mode: str) -> str:
    """Run poppler's pdftotext over the bytes via stdin/stdout. mode: 'layout'|'raw'."""
    flag = "-layout" if mode == "layout" else "-raw"
    proc = subprocess.run(
        [_PDFTOTEXT, flag, "-", "-"],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    return proc.stdout.decode("utf-8", errors="replace")


def _pypdf(data: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_text(data: bytes, mode: str = "layout") -> str:
    """PDF bytes -> plain text. mode 'layout' (tables) or 'raw' (reading order).

    Prefers poppler's pdftotext when present (much better column/geometry handling),
    falls back to pypdf. Returns "" on any failure — never raises.
    """
    if not data:
        return ""
    if _PDFTOTEXT:
        try:
            return _pdftotext(data, mode)
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("pdftotext_failed", error=str(exc))
    try:
        return _pypdf(data)
    except Exception as exc:  # noqa: BLE001 — any pypdf failure → empty text
        logger.warning("pypdf_failed", error=str(exc))
        return ""
