"""Request/response shapes for the PDF markup feature."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class UploadDrawingRequest:
    file_bytes: bytes
    filename: Optional[str]
    mime_type: str
    note: Optional[str] = None
    source_version_id: Optional[int] = None


PDF_MAGIC = b'%PDF-'


def is_pdf_bytes(data: bytes) -> bool:
    return bool(data) and data[:5] == PDF_MAGIC
