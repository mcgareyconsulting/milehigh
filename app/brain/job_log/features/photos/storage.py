"""Filesystem storage helpers for release photos.

Mirrors the PDF markup storage module so the same swap point applies. Storage
keys are repo-relative paths like "<release_id>/<photo_id>.<ext>".
"""

import os
import tempfile
from pathlib import Path

from flask import current_app

_MIME_EXTENSIONS = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/heic': '.heic',
    'image/heif': '.heic',
    'image/tiff': '.tif',
}


def _storage_root() -> Path:
    override = current_app.config.get('PHOTO_STORAGE_ROOT')
    if override:
        return Path(override)
    return Path(current_app.root_path) / 'storage' / 'photos'


def _release_dir(release_id: int) -> Path:
    return _storage_root() / str(release_id)


def extension_for_mime(mime_type: str) -> str:
    return _MIME_EXTENSIONS.get((mime_type or '').lower(), '.jpg')


def absolute_path(storage_key: str) -> Path:
    return _storage_root() / storage_key


def save_photo(release_id: int, name: str, data: bytes) -> str:
    """Atomically write the image and return its repo-relative storage_key.

    `name` is the final filename (e.g. "<photo_id>.jpg").
    """
    release_dir = _release_dir(release_id)
    release_dir.mkdir(parents=True, exist_ok=True)
    final_path = release_dir / name

    fd, tmp_path = tempfile.mkstemp(prefix='photo_', suffix='.tmp', dir=str(release_dir))
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

    return f"{release_id}/{name}"


def delete_photo_file(storage_key: str) -> None:
    """Best-effort unlink; safe to call when the file is already gone."""
    try:
        absolute_path(storage_key).unlink()
    except FileNotFoundError:
        pass
