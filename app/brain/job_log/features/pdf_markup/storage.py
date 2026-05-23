"""Filesystem storage helpers for PDF markup versions.

Single swap point — replace these four functions to migrate to OneDrive/S3.
Storage keys are repo-relative paths like "<release_id>/v<n>.pdf".
"""

import os
import tempfile
from pathlib import Path

from flask import current_app


def _storage_root() -> Path:
    override = current_app.config.get('PDF_STORAGE_ROOT')
    if override:
        return Path(override)
    return Path(current_app.root_path) / 'storage' / 'pdfs'


def _release_dir(release_id: int) -> Path:
    return _storage_root() / str(release_id)


def absolute_path(storage_key: str) -> Path:
    return _storage_root() / storage_key


def save_pdf(release_id: int, version: int, data: bytes) -> str:
    """Atomically write the PDF and return its repo-relative storage_key."""
    release_dir = _release_dir(release_id)
    release_dir.mkdir(parents=True, exist_ok=True)
    final_path = release_dir / f"v{version}.pdf"

    fd, tmp_path = tempfile.mkstemp(prefix=f"v{version}_", suffix=".pdf.tmp", dir=str(release_dir))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return f"{release_id}/v{version}.pdf"


def read_pdf(storage_key: str) -> bytes:
    return absolute_path(storage_key).read_bytes()


def delete_pdf_file(storage_key: str) -> None:
    """Best-effort unlink; safe to call when the file is already gone."""
    try:
        absolute_path(storage_key).unlink()
    except FileNotFoundError:
        pass


def pdf_exists_for_release(release_id: int) -> bool:
    return _release_dir(release_id).exists()
