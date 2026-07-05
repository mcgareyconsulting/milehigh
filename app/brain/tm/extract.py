"""Claude-vision extraction of a T&M ticket document into structured fields.

v1 sends EVERY upload straight to vision — a PDF goes as a native document
block (Anthropic extracts text AND rasterizes server-side), an image goes as an
image block. Tickets are 1-2 pages, so there's no text-layer routing; if volume
ever justifies it, a cheap born-digital text route can slot in front.

Mirrors app/brain/material_orders/extractors/llm.py: raw `requests`,
ANTHROPIC_API_KEY, strict-JSON prompt. Unlike that extractor this one RAISES on
failure — the route catches and still creates the ticket (blank, carrying
extract_error) so a failed extraction never loses the uploaded document.

The model also self-reports per-field confidence (0-1). Treat it as a
HIGHLIGHTING heuristic for the review modal, never a gate — the human confirm
is the gate.
"""
import base64
import json
import os
import re

import requests

from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
EXTRACT_MODEL = os.environ.get("TM_TICKET_EXTRACT_MODEL", "claude-opus-4-8")
MAX_DOC_BYTES = 20 * 1024 * 1024  # Anthropic document/image block ceiling guard

_SYSTEM = (
    "You read Time & Material (T&M) field tickets for Mile High Metal Works, a "
    "miscellaneous-metals fabricator. Tickets are usually a single handwritten page "
    "(sometimes a scan or photo) recording extra work performed on a construction "
    "site: who worked, what hours, what materials and equipment were used, what was "
    "done, and a customer signature. Extract every field you can read. Transcribe "
    "handwriting faithfully; when a value is absent or illegible use null rather "
    "than guessing. Dates must be ISO YYYY-MM-DD. Hours are numbers. "
    "job_number is the numeric job number if the ticket shows one (e.g. '580' from "
    "'580-659' style markings; the part before a dash is the job). "
    "Also self-assess confidence 0-1 for each top-level field: 1.0 = printed text "
    "read cleanly, lower for messy handwriting or inference. "
    "Return STRICT JSON only, no prose, no markdown. Schema: "
    '{"job_number": int|null, "date_of_work": "YYYY-MM-DD"|null, "customer": str|null, '
    '"work_description": str|null, '
    '"labor": [{"name": str, "company": str|null, "classification": str|null, '
    '"hours_reg": number|null, "hours_ot": number|null, "hours_dt": number|null, '
    '"notes": str|null}], '
    '"materials": [{"description": str, "quantity": number|null, "unit": str|null, '
    '"length": str|null, "notes": str|null}], '
    '"equipment": [{"description": str, "quantity": number|null, "hours": number|null, '
    '"operator": str|null, "notes": str|null}], '
    '"signature_present": bool, "signature_name": str|null, '
    '"confidence": {"job_number": number, "date_of_work": number, "customer": number, '
    '"work_description": number, "labor": number, "materials": number, '
    '"equipment": number, "signature": number}}'
)


def _content_block(data: bytes, media_type: str) -> dict:
    b64 = base64.standard_b64encode(data).decode("ascii")
    if media_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}


def _call_anthropic(data: bytes, media_type: str) -> dict:
    key = cfg.ANTHROPIC_API_KEY
    if not key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    if len(data) > MAX_DOC_BYTES:
        raise ValueError(f"document too large for extraction ({len(data)} bytes)")
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
            "system": _SYSTEM,
            "messages": [{
                "role": "user",
                "content": [
                    _content_block(data, media_type),
                    {"type": "text", "text": "Extract this T&M ticket."},
                ],
            }],
        },
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    text = "".join(b.get("text", "") for b in body.get("content", []))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0) if m else text)


def _num(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _entries(raw, fields) -> list:
    """Normalize a list of extracted line dicts to known keys only."""
    out = []
    for ln in raw if isinstance(raw, list) else []:
        if not isinstance(ln, dict):
            continue
        entry = {}
        for key, kind in fields.items():
            v = ln.get(key)
            entry[key] = _num(v) if kind == "num" else ((str(v).strip() or None) if v is not None else None)
        if any(v not in (None, "") for v in entry.values()):
            out.append(entry)
    return out


def extract(data: bytes, media_type: str) -> dict:
    """Extract a T&M ticket document. Returns {fields..., confidence, raw}.

    Raises on any failure (missing key, API error, unparseable output) — the
    caller decides what a failed extraction means for the ticket.
    """
    raw = _call_anthropic(data, media_type)
    if not isinstance(raw, dict):
        raise ValueError("extraction returned non-object JSON")

    job = raw.get("job_number")
    try:
        job = int(job) if job is not None else None
    except (TypeError, ValueError):
        job = None

    date_of_work = raw.get("date_of_work")
    if date_of_work is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date_of_work)):
        date_of_work = None

    confidence = raw.get("confidence") if isinstance(raw.get("confidence"), dict) else {}

    return {
        "job": job,
        "date_of_work": date_of_work,
        "customer": (raw.get("customer") or None),
        "work_description": (raw.get("work_description") or None),
        "labor": _entries(raw.get("labor"), {
            "name": "str", "company": "str", "classification": "str",
            "hours_reg": "num", "hours_ot": "num", "hours_dt": "num", "notes": "str",
        }),
        "materials": _entries(raw.get("materials"), {
            "description": "str", "quantity": "num", "unit": "str",
            "length": "str", "notes": "str",
        }),
        "equipment": _entries(raw.get("equipment"), {
            "description": "str", "quantity": "num", "hours": "num",
            "operator": "str", "notes": "str",
        }),
        "signature_present": bool(raw.get("signature_present")),
        "signature_name": (raw.get("signature_name") or None),
        "confidence": confidence,
        "raw": raw,
    }
