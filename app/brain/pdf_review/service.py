"""Banana Boy PDF-review Claude call.

Hands the full For-Construction drawing set to Claude as a base64 document block
(Claude reads PDFs natively, so cross-sheet reasoning works — a rise on one sheet,
a tread spec on another) and asks for strict-JSON compliance findings against the
rule library in `rules.py`.

Mirrors app/brain/material_orders/extractors/llm.py: raw `requests`, ANTHROPIC_API_KEY
from Config, model claude-opus-4-8, and a graceful return of None on a missing key or
ANY failure, so the feature (and tests) stay hermetic without a key. Runs on a
background thread (see worker.py) — the call takes minutes at adaptive-thinking depth.
"""
import base64
import json
import os
import re

import requests

from app.config import Config as cfg
from app.logging_config import get_logger
from app.brain.pdf_review.rules import build_system_prompt, USER_INSTRUCTION

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
REVIEW_MODEL = os.environ.get("BB_PDF_REVIEW_MODEL", "claude-opus-4-8")
MAX_PDF_BYTES = 32 * 1024 * 1024  # Anthropic document-block ceiling
# The set is large and the reasoning is deep; adaptive thinking consumes most of the
# budget (observed ~25k output on a 24-page set), so give generous headroom.
MAX_TOKENS = int(os.environ.get("BB_PDF_REVIEW_MAX_TOKENS", "32000"))
REQUEST_TIMEOUT = 600


def _content_blocks(pdf_bytes: bytes, job_release: str) -> list:
    return [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf_bytes).decode("ascii"),
            },
        },
        {"type": "text", "text": USER_INSTRUCTION.format(job_release=job_release or "unknown")},
    ]


def _call_anthropic(pdf_bytes: bytes, job_release: str) -> dict:
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
            "model": REVIEW_MODEL,
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "adaptive"},
            "system": build_system_prompt(),
            "messages": [{"role": "user", "content": _content_blocks(pdf_bytes, job_release)}],
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    usage = body.get("usage") or {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in response (stop_reason={body.get('stop_reason')})")
    data = json.loads(m.group(0))
    return {
        "findings": data.get("findings") or [],
        "model": body.get("model") or REVIEW_MODEL,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


def review(pdf_bytes: bytes, job_release: str):
    """Return {findings, model, input_tokens, output_tokens}, or None on no key / any failure.

    `findings` is a list of dicts (rule_id, issue, verdict, severity, computation,
    values_used, evidence, location). Empty list means BB reviewed and found nothing.
    """
    if not pdf_bytes or len(pdf_bytes) > MAX_PDF_BYTES:
        logger.info("bb_pdf_review_skipped", reason="empty or over size ceiling",
                    size=len(pdf_bytes) if pdf_bytes else 0)
        return None
    try:
        result = _call_anthropic(pdf_bytes, job_release)
    except Exception as e:  # noqa: BLE001 — any failure → no result; caller records the error
        logger.info("bb_pdf_review_failed", error=str(e))
        return None
    logger.info("bb_pdf_review_complete", job_release=job_release,
                findings=len(result["findings"]),
                input_tokens=result.get("input_tokens"), output_tokens=result.get("output_tokens"))
    return result
