"""Server-side cache of pulled Procore submittal drawings.

Once a submittal's drawing has been pulled from Procore, its bytes are cached here so a
BB review (or a re-review on a different model) can run without re-pulling. Keyed by the
(Procore submittal id, prostore attachment id) pair — a submittal can carry more than one
reviewable drawing, so each attachment gets its own file under the submittal's folder:
    procore_submittals/<submittal_id>/<attachment_id>.pdf
Uses the same PDF_STORAGE_ROOT swap point as the markup storage.
"""
import os
import tempfile
from pathlib import Path

from flask import current_app


def _root() -> Path:
    override = current_app.config.get("PDF_STORAGE_ROOT")
    base = Path(override) if override else Path(current_app.root_path) / "storage" / "pdfs"
    return base / "procore_submittals"


def _path(submittal_id, attachment_id) -> Path:
    return _root() / str(submittal_id) / f"{str(attachment_id)}.pdf"


def save(submittal_id, attachment_id, data: bytes) -> None:
    """Atomically cache the pulled PDF for one (submittal, attachment)."""
    path = _path(submittal_id, attachment_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".pdf.tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read(submittal_id, attachment_id):
    """Return the cached PDF bytes for a (submittal, attachment), or None if not cached."""
    path = _path(submittal_id, attachment_id)
    return path.read_bytes() if path.exists() else None


def meta(submittal_id, attachment_id):
    """Return {'size_bytes': int} for a cached (submittal, attachment) drawing, or None."""
    path = _path(submittal_id, attachment_id)
    if not path.exists():
        return None
    return {"size_bytes": path.stat().st_size}


def list_cached(submittal_id):
    """Return the attachment ids (as strings) that have a cached PDF for a submittal.

    Filesystem-only (no Procore call). Lets the legacy submittal-level endpoints, which
    don't track a specific attachment, discover what's already been pulled.
    """
    folder = _root() / str(submittal_id)
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.pdf"))
