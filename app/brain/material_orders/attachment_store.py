"""Content-addressed storage for supplier-order email attachments (PDFs).

The lake captures attachment text into the RawSourceRecord payload for the
deterministic extractors, but the LLM extractor wants the *original* PDF bytes so
it can hand Claude a native document block (drawings don't survive text
extraction). We persist the raw bytes here, keyed by content hash, and carry the
returned `storage_key` in the payload attachment dict.

Single swap point — mirror app/brain/job_log/features/pdf_markup/storage.py;
replace these functions to move to OneDrive/S3. Storage keys are repo-relative
paths like "ab/cd/<sha256>.pdf". Works with or without a Flask app context (falls
back to a temp dir) so the .eml adapter can store during pure-parser tests too.
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


def _storage_root() -> Path:
    if has_app_context():
        override = current_app.config.get("MATERIAL_ORDER_STORAGE_ROOT")
        if override:
            return Path(override)
        return Path(current_app.root_path) / "storage" / "order_attachments"
    return Path(tempfile.gettempdir()) / "mhmw_order_attachments"


def absolute_path(storage_key: str) -> Path:
    return _storage_root() / storage_key


def save(data: bytes) -> str:
    """Atomically write the bytes content-addressed by sha256; return the storage_key.

    Idempotent — the same bytes always map to the same key, so re-ingesting an
    attachment is a no-op overwrite.
    """
    digest = hashlib.sha256(data).hexdigest()
    storage_key = f"{digest[:2]}/{digest[2:4]}/{digest}.pdf"
    final_path = absolute_path(storage_key)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf.tmp", dir=str(final_path.parent))
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
    """Read attachment bytes back, or b"" if the file is missing (e.g. other host)."""
    try:
        return absolute_path(storage_key).read_bytes()
    except (FileNotFoundError, OSError):
        return b""
