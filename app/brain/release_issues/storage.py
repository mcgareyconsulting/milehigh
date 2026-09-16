"""Filesystem storage for release issue attachments (photos + PDFs).

    <RELEASE_ISSUE_STORAGE_ROOT>/<issue_id>/<attachment_id>.<ext>

Storage keys are root-relative ("<issue_id>/<attachment_id>.<ext>"). Mirrors the
photo storage modules so the same swap point applies when K3 (object storage)
lands. Local dev (no env set) falls back to <app>/storage/release_issues.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from flask import current_app

from app.brain.job_log.features.photos.payloads import is_probably_image, sniff_image_mime

_MIME_EXTENSIONS = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/heic': '.heic',
    'image/heif': '.heic',
    'image/tiff': '.tif',
    'application/pdf': '.pdf',
}


def sniff_mime(data: bytes, mimetype: str, filename: str) -> Optional[str]:
    """Resolve an upload to an accepted mime type, or None if it is not a photo/PDF."""
    if data[:5] == b'%PDF-':
        return 'application/pdf'
    sniffed = sniff_image_mime(data)
    if sniffed:
        return sniffed
    if is_probably_image(data, mimetype, filename):
        declared = (mimetype or '').lower()
        return declared if declared.startswith('image/') else 'image/jpeg'
    return None


def _storage_root() -> Path:
    override = current_app.config.get('RELEASE_ISSUE_STORAGE_ROOT')
    if override:
        return Path(override)
    return Path(current_app.root_path) / 'storage' / 'release_issues'


def extension_for_mime(mime_type: str) -> str:
    return _MIME_EXTENSIONS.get((mime_type or '').lower(), '.bin')


def absolute_path(storage_key: str) -> Path:
    return _storage_root() / storage_key


def save_attachment(issue_id: int, name: str, data: bytes) -> str:
    """Atomically write the file and return its root-relative storage_key."""
    issue_dir = _storage_root() / str(issue_id)
    issue_dir.mkdir(parents=True, exist_ok=True)
    final_path = issue_dir / name

    fd, tmp_path = tempfile.mkstemp(prefix='issue_attach_', suffix='.tmp', dir=str(issue_dir))
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

    return f"{issue_id}/{name}"
