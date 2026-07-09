"""LLM fallback extractor — Claude reads the email (and PDF natively) for novel shapes.

The deterministic extractors cover the known-clean shapes cheaply; this catches
everything else (new suppliers, drawing variants pdftotext mangles, odd layouts).
It hands Claude the email body plus each order PDF as a base64 document block —
Claude reads PDFs directly, sidestepping the scrambled-text problem — and asks for
strict-JSON line items. Deterministic header fields (supplier, PO, orderer) are
trusted over the model; only the line items + supplier order # come from the LLM.

Mirrors app/brain/meetings/extract.py: raw `requests`, ANTHROPIC_API_KEY, and a
graceful return of None on a missing key or ANY failure, so the pipeline (and
tests) stay hermetic without a key. The model defaults to claude-sonnet-5 — this
is a structured-extraction task, so Sonnet gives near-Opus quality at a fraction
of the cost; override with MATERIAL_ORDER_EXTRACT_MODEL. Thinking is disabled so
this stays a fast, deterministic extractor: Sonnet 5 runs *adaptive* thinking when
the field is omitted, which would add billed thinking tokens on every call.
"""
import base64
import json
import os
import re

import requests

from app.brain.material_orders import attachment_store, parser
from app.brain.material_orders.extractors import base
from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)

NAME = "llm"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
EXTRACT_MODEL = os.environ.get("MATERIAL_ORDER_EXTRACT_MODEL", "claude-sonnet-5")
MAX_PDF_BYTES = 20 * 1024 * 1024  # Anthropic document-block ceiling guard

_SYSTEM = (
    "You read supplier material-order emails for Mile High Metal Works, a structural-"
    "steel fabricator, and extract the ordered line items. The order may be typed in "
    "the email body or contained in an attached PDF (an order confirmation or a CAD "
    "drawing whose part marks carry quantity callouts). Extract every distinct ordered "
    "part. For each line: quantity (number), description (full part text, authoritative), "
    "and when present profile, gauge, finish, dimension, unit_price, extended_price. "
    "Also return supplier_order_no (the supplier's own order/confirmation number if the "
    "document shows one, else null) and event_type ('confirmed' if this is the supplier "
    "confirming/acknowledging an order, otherwise 'placed'). "
    "Return STRICT JSON only, no prose, no markdown. Schema: "
    '{"lines":[{"quantity":number,"description":str,"profile":str|null,"gauge":str|null,'
    '"finish":str|null,"dimension":str|null,"unit_price":number|null,'
    '"extended_price":number|null}],"supplier_order_no":str|null,'
    '"event_type":"placed"|"confirmed"}'
)


def _content_blocks(record):
    """Email body text + a base64 document block per order PDF (bytes when available)."""
    payload = record.payload or {}
    body = parser._html_to_text(payload.get("body"), payload.get("body_content_type"))
    blocks = []
    for att in base.attachments(record):
        key = att.get("storage_key")
        data = attachment_store.read(key) if key else b""
        if data and len(data) <= MAX_PDF_BYTES:
            blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(data).decode("ascii"),
                },
            })
        elif (att.get("text") or "").strip():
            blocks.append({"type": "text", "text": f"[ATTACHMENT {att.get('filename')}]\n{att['text']}"})
    subject = (payload.get("subject") or "").strip()
    blocks.append({"type": "text", "text": f"Subject: {subject}\n\n{body}"})
    return blocks


def _call_anthropic(record):
    key = cfg.ANTHROPIC_API_KEY
    if not key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": EXTRACT_MODEL,
            "max_tokens": 4096,
            # Keep this a pure extractor. Opus omits thinking when the field is
            # absent, but Sonnet 5 defaults to adaptive thinking — disable it
            # explicitly so we don't pay for thinking tokens on every call.
            "thinking": {"type": "disabled"},
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": _content_blocks(record)}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    text = "".join(b.get("text", "") for b in body.get("content", []))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0) if m else text)


def extract(record):
    """Return a normalized order dict, or None on no key / any failure / no lines."""
    try:
        data = _call_anthropic(record)
    except Exception as e:  # noqa: BLE001 — any failure → no LLM result, deterministic path stands
        logger.info("material_order_llm_fallback_skipped", error=str(e))
        return None

    raw_lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(raw_lines, list) or not raw_lines:
        return None

    lines = []
    for ln in raw_lines:
        if not isinstance(ln, dict) or ln.get("quantity") is None:
            continue
        description = (ln.get("description") or "").strip()
        lines.append({
            "quantity": float(ln["quantity"]),
            "description": description,
            "profile": ln.get("profile"),
            "gauge": ln.get("gauge"),
            "finish": ln.get("finish"),
            "dimension": ln.get("dimension"),
            "unit_price": ln.get("unit_price"),
            "extended_price": ln.get("extended_price"),
            "raw_line": description[:512],
            "line_index": len(lines),
        })
    if not lines:
        return None

    header = parser.extract_header(record.payload or {})
    event_type = data.get("event_type") if data.get("event_type") in ("placed", "confirmed") else "placed"
    return base.order(
        header,
        event_type=event_type,
        lines=lines,
        supplier_order_no=data.get("supplier_order_no") or None,
    )
