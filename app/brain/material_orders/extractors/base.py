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


def order(header, *, event_type, lines, supplier_order_no=None,
          order_kind="material", shipping_status=None):
    """Assemble a normalized order dict from a header + extracted lines.

    order_kind/shipping_status are order-level and stamped onto every line row by
    the service: 'material' rows leave shipping_status null (their lifecycle is the
    ordered/received status), while 'galvanizing'/'stock' status notifications carry
    a planning→complete shipping_status for the shipping-planning lane.
    """
    header.pop("_haystack", None)
    return {
        **header,
        "event_type": event_type,
        "supplier_order_no": supplier_order_no,
        "order_kind": order_kind,
        "shipping_status": shipping_status,
        "lines": lines,
    }
