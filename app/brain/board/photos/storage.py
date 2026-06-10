"""Filesystem storage helpers for board item photos.

Mirrors the release photo storage module (`app/brain/job_log/features/photos/
storage.py`) but keys files under a dedicated `board/` subtree so board and
release photos never collide:

    <PHOTO_STORAGE_ROOT>/board/<item_id>/<photo_id>.<ext>

Storage keys are root-relative paths like "board/<item_id>/<photo_id>.<ext>".
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


def _item_dir(item_id: int) -> Path:
    return _storage_root() / 'board' / str(item_id)


def extension_for_mime(mime_type: str) -> str:
    return _MIME_EXTENSIONS.get((mime_type or '').lower(), '.jpg')


def absolute_path(storage_key: str) -> Path:
    return _storage_root() / storage_key


def save_photo(item_id: int, name: str, data: bytes) -> str:
    """Atomically write the image and return its root-relative storage_key.

    `name` is the final filename (e.g. "<photo_id>.jpg").
    """
    item_dir = _item_dir(item_id)
    item_dir.mkdir(parents=True, exist_ok=True)
    final_path = item_dir / name

    fd, tmp_path = tempfile.mkstemp(prefix='photo_', suffix='.tmp', dir=str(item_dir))
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

    return f"board/{item_id}/{name}"


def delete_photo_file(storage_key: str) -> None:
    """Best-effort unlink; safe to call when the file is already gone."""
    try:
        absolute_path(storage_key).unlink()
    except FileNotFoundError:
        pass
