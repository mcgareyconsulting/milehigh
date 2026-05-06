"""Request/response shapes for the PDF markup feature."""

PDF_MAGIC = b'%PDF-'


def is_pdf_bytes(data: bytes) -> bool:
    return bool(data) and data[:5] == PDF_MAGIC
