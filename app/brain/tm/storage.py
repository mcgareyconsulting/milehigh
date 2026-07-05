"""Content-addressed storage for uploaded T&M ticket documents (PDFs and images).

Mirrors app/brain/material_orders/attachment_store.py (the single-swap-point
pattern — replace these functions to move to OneDrive/S3), generalized to carry
the original file extension so the review modal can serve images and PDFs with
the right content type. Storage keys are repo-relative paths like
"ab/cd/<sha256>.<ext>". Works with or without a Flask app context (falls back
to a temp dir) so pure-parser tests can store too.
"""
import hashlib
import os
import tempfile
from pathlib import Path

try:
    from flask import current_app, has_app_context
except ImportError:  # pragma: no cover - flask always present in this app
    current_app = None

    def has_app_context():
        return False


# media_type -> storage extension; also the upload allowlist.
MEDIA_TYPE_EXTENSIONS = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _storage_root() -> Path:
    if has_app_context():
        override = current_app.config.get("TM_TICKET_STORAGE_ROOT")
        if override:
            return Path(override)
        return Path(current_app.root_path) / "storage" / "tm_tickets"
    return Path(tempfile.gettempdir()) / "mhmw_tm_tickets"


def absolute_path(storage_key: str) -> Path:
    return _storage_root() / storage_key


def save(data: bytes, media_type: str) -> str:
    """Atomically write the bytes content-addressed by sha256; return the storage_key.

    Idempotent — the same bytes always map to the same key, so re-uploading the
    same document is a no-op overwrite.
    """
    ext = MEDIA_TYPE_EXTENSIONS.get(media_type)
    if ext is None:
        raise ValueError(f"unsupported media type: {media_type}")
    digest = hashlib.sha256(data).hexdigest()
    storage_key = f"{digest[:2]}/{digest[2:4]}/{digest}.{ext}"
    final_path = absolute_path(storage_key)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}.tmp", dir=str(final_path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return storage_key


def read(storage_key: str) -> bytes:
    """Read document bytes back, or b"" if the file is missing (e.g. other host)."""
    try:
        return absolute_path(storage_key).read_bytes()
    except (FileNotFoundError, OSError):
        return b""
