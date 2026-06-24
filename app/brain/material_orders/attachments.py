"""Normalize a raw email attachment into the payload attachment dict.

One seam shared by both ingestion sources so they land identical shapes:
- app/lake/ingest/m365_mail.py — bytes fetched from Microsoft Graph
- app/brain/material_orders/eml_adapter.py — bytes pulled from a saved .eml

Each attachment becomes {filename, content_type, size, text, storage_key}: `text`
is the extracted PDF text the deterministic extractors read; `storage_key` points
at the persisted original bytes the LLM extractor re-reads as a document block.
Non-PDF attachments (inline signature images etc.) are skipped — they carry no
order data and would only bloat the lake record.
"""
from app.brain.material_orders import attachment_store, pdf_text
from app.logging_config import get_logger

logger = get_logger(__name__)


def _is_pdf(filename: str, content_type: str) -> bool:
    return (content_type or "").lower() == "application/pdf" or (
        filename or ""
    ).lower().endswith(".pdf")


def build_attachment(filename: str, content_type: str, data: bytes):
    """(filename, content_type, bytes) -> payload attachment dict, or None to skip."""
    if not data or not _is_pdf(filename, content_type):
        return None
    try:
        storage_key = attachment_store.save(data)
    except OSError as exc:  # persistence is best-effort; text still works without bytes
        logger.warning("attachment_store_failed", filename=filename, error=str(exc))
        storage_key = None
    return {
        "filename": filename or "",
        "content_type": content_type or "application/pdf",
        "size": len(data),
        "text": pdf_text.extract_text(data),
        "storage_key": storage_key,
    }
