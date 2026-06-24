"""Shared helpers for the order extractors — attachment access + result shaping."""
from app.brain.material_orders import attachment_store, pdf_text


def attachments(record):
    """The payload's attachment dicts ({filename, content_type, size, text, storage_key})."""
    return (record.payload or {}).get("attachments") or []


def pdf_attachments(record):
    """Attachments that carry usable extracted text (the order PDFs)."""
    return [a for a in attachments(record) if (a.get("text") or "").strip()]


def raw_text(attachment):
    """Reading-order ('-raw') text for an attachment — re-extracted from the stored
    original bytes (drawings need raw order, not the layout text in the payload).
    Falls back to the payload's layout text when the bytes aren't on this host.
    """
    key = attachment.get("storage_key")
    if key:
        data = attachment_store.read(key)
        if data:
            return pdf_text.extract_text(data, mode="raw")
    return attachment.get("text") or ""


def order(header, *, event_type, lines, supplier_order_no=None):
    """Assemble a normalized order dict from a header + extracted lines."""
    header.pop("_haystack", None)
    return {
        **header,
        "event_type": event_type,
        "supplier_order_no": supplier_order_no,
        "lines": lines,
    }
