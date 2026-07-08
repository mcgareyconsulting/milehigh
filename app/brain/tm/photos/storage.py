"""Filesystem storage helpers for T&M ticket photo/video attachments.

Mirrors app/brain/board/photos/storage.py but keys files under a dedicated
`tm/` subtree and extends the mime map with common video formats:

    <PHOTO_STORAGE_ROOT>/tm/<ticket_id>/<attachment_id>.<ext>

Storage keys are root-relative paths like "tm/<ticket_id>/<attachment_id>.<ext>".
Reuses the same PHOTO_STORAGE_ROOT config key as board photos — they never
collide since each writes under its own subtree.
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
    'video/mp4': '.mp4',
    'video/quicktime': '.mov',
    'video/webm': '.webm',
    'video/3gpp': '.3gp',
}


def _storage_root() -> Path:
    override = current_app.config.get('PHOTO_STORAGE_ROOT')
    if override:
        return Path(override)
    return Path(current_app.root_path) / 'storage' / 'photos'


def _ticket_dir(ticket_id: int) -> Path:
    return _storage_root() / 'tm' / str(ticket_id)


def extension_for_mime(mime_type: str) -> str:
    return _MIME_EXTENSIONS.get((mime_type or '').lower(), '.bin')


def absolute_path(storage_key: str) -> Path:
    return _storage_root() / storage_key


def save_attachment(ticket_id: int, name: str, data: bytes) -> str:
    """Atomically write the file and return its root-relative storage_key.

    `name` is the final filename (e.g. "<attachment_id>.jpg").
    """
    ticket_dir = _ticket_dir(ticket_id)
    ticket_dir.mkdir(parents=True, exist_ok=True)
    final_path = ticket_dir / name

    fd, tmp_path = tempfile.mkstemp(prefix='tm_attach_', suffix='.tmp', dir=str(ticket_dir))
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

    return f"tm/{ticket_id}/{name}"


def delete_attachment_file(storage_key: str) -> None:
    """Best-effort unlink; safe to call when the file is already gone."""
    try:
        absolute_path(storage_key).unlink()
    except FileNotFoundError:
        pass
