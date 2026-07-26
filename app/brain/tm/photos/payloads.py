"""Image/video sniffing/validation for T&M ticket attachment uploads.

We accept common raster images (reusing the release-photo sniffer) and common
video formats. Validation prefers magic bytes but falls back to the declared
mimetype/filename extension so phone-camera formats (HEIC stills, MOV clips)
still go through.
"""
from typing import Optional

from app.brain.job_log.features.photos.payloads import sniff_image_mime, is_probably_image

_VIDEO_EXTENSIONS = ('.mp4', '.mov', '.webm', '.3gp', '.m4v')

# ISO-BMFF "ftyp" brand codes that indicate video (as opposed to HEIC/HEIF stills,
# which use a distinct brand set already handled by sniff_image_mime).
_FTYP_VIDEO_BRANDS = (
    b'isom', b'iso2', b'mp41', b'mp42', b'avc1', b'M4V ', b'M4A ',
    b'qt  ', b'3gp4', b'3gp5', b'3g2a', b'mmp4',
)


def sniff_video_mime(data: bytes) -> Optional[str]:
    """Return a video mime type from magic bytes, or None if unrecognized."""
    if not data or len(data) < 12:
        return None
    if data[:4] == b'\x1a\x45\xdf\xa3':
        return 'video/webm'
    if data[4:8] == b'ftyp':
        brand = data[8:12]
        if brand == b'qt  ':
            return 'video/quicktime'
        if brand in _FTYP_VIDEO_BRANDS:
            return 'video/mp4'
    return None


def is_probably_video(data: bytes, mimetype: str, filename: str) -> bool:
    """True if the upload looks like a video by magic bytes, mimetype, or name."""
    if sniff_video_mime(data):
        return True
    if mimetype and mimetype.lower().startswith('video/'):
        return True
    return (filename or '').lower().endswith(_VIDEO_EXTENSIONS)


def sniff_media_mime(data: bytes) -> Optional[str]:
    return sniff_image_mime(data) or sniff_video_mime(data)


def is_probably_media(data: bytes, mimetype: str, filename: str) -> bool:
    """True if the upload looks like an image or a video."""
    return is_probably_image(data, mimetype, filename) or is_probably_video(data, mimetype, filename)
