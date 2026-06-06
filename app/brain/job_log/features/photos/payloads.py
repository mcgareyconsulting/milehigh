"""Image sniffing/validation for release photo uploads.

We accept any common raster image. Validation prefers magic bytes but falls
back to the declared mimetype / filename extension so phone-camera formats
(e.g. HEIC) still go through.
"""

from typing import Optional

_IMAGE_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.heic', '.heif', '.tif', '.tiff',
)


def sniff_image_mime(data: bytes) -> Optional[str]:
    """Return a mime type from magic bytes, or None if unrecognized."""
    if not data or len(data) < 12:
        return None
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:2] == b'BM':
        return 'image/bmp'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    # HEIC/HEIF and other ISO-BMFF: "ftyp" box brand at offset 4.
    if data[4:8] == b'ftyp':
        brand = data[8:12]
        if brand in (b'heic', b'heix', b'hevc', b'heim', b'heis', b'mif1', b'msf1'):
            return 'image/heic'
    return None


def is_probably_image(data: bytes, mimetype: str, filename: str) -> bool:
    """True if the upload looks like an image by magic bytes, mimetype, or name."""
    if sniff_image_mime(data):
        return True
    if mimetype and mimetype.lower().startswith('image/'):
        return True
    name = (filename or '').lower()
    return name.endswith(_IMAGE_EXTENSIONS)
