"""Carmen Miranda PDF-review Claude call.

Hands the full For-Construction drawing set to Claude as a base64 document block
(Claude reads PDFs natively, so cross-sheet reasoning works — a rise on one sheet,
a tread spec on another) and asks for strict-JSON compliance findings against the
rule library in `rules.py`.

Mirrors app/brain/material_orders/extractors/llm.py: raw `requests`, ANTHROPIC_API_KEY
from Config, model claude-opus-4-8, and a graceful return of None on a missing key or
ANY failure. The findings come back under `output_config.format` (a schema the API
enforces), not as JSON fished out of prose, so the feature (and tests) stay hermetic without a key. Runs on a
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
# Friendly names → model ids so callers (endpoint/UI) can ask for a lighter Sonnet review
# vs the deep Opus one. Both take the same request shape (adaptive thinking + PDF blocks).
MODEL_ALIASES = {
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-4-8",
}


def resolve_model(name):
    """Map a friendly alias ('sonnet'/'opus') or a raw model id to a model id.
    Falls back to the configured REVIEW_MODEL when name is empty/unknown-but-blank."""
    if not name:
        return REVIEW_MODEL
    return MODEL_ALIASES.get(str(name).strip().lower(), str(name).strip())


MAX_PDF_BYTES = 32 * 1024 * 1024  # Anthropic document-block ceiling
# The set is large and the reasoning is deep; adaptive thinking consumes most of the
# budget (observed ~25k output on a 24-page set), so give generous headroom.
MAX_TOKENS = int(os.environ.get("BB_PDF_REVIEW_MAX_TOKENS", "32000"))
REQUEST_TIMEOUT = 600


# The findings contract, as a schema the API enforces rather than a shape we ask for in
# prose and then dig out of the reply with a regex. That older approach broke on the
# domain's own vocabulary: the prompt asks Claude to quote exact dimension text, so a
# finding reading `terminal rise 8" exceeds 7"` put raw quotes inside a JSON string and
# json.loads died mid-object. Under `output_config.format` the inch marks come back
# properly escaped. Optional fields are deliberately NOT in `required` — the prompt asks
# for bare rule_id + issue on 'ok' entries, and forcing every key would fight that.
FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "page": {"type": "integer"},
                    "issue": {"type": "string"},
                    "verdict": {"enum": ["violation", "ok", "needs_field_verification"]},
                    "severity": {"enum": ["high", "medium", "low"]},
                    "computation": {"type": "string"},
                    "values_used": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "sheet": {"type": "string"},
                            },
                            "required": ["name", "value"],
                            "additionalProperties": False,
                        },
                    },
                    "location": {"type": "string"},
                },
                "required": ["rule_id", "issue", "verdict"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}


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


def _parse_findings(text: str, stop_reason=None) -> dict:
    """The response body as a dict. Schema-constrained, so plain json.loads is the path.

    The regex fallback stays for the two cases the schema cannot cover — a truncated
    reply (`max_tokens`) and a refusal, where the text is not schema-shaped. It logs the
    raw text when everything fails: this class of bug is undebuggable without seeing what
    came back, and the old code discarded it.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    logger.error("bb_pdf_review_unparseable", stop_reason=stop_reason,
                 response_text=(text or "")[:2000])
    raise ValueError(f"could not parse findings (stop_reason={stop_reason})")


def _call_anthropic(pdf_bytes: bytes, job_release: str, model: str = None) -> dict:
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
            "model": model or REVIEW_MODEL,
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "adaptive"},
            "output_config": {"format": {"type": "json_schema", "schema": FINDINGS_SCHEMA}},
            "system": build_system_prompt(),
            "messages": [{"role": "user", "content": _content_blocks(pdf_bytes, job_release)}],
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    usage = body.get("usage") or {}
    stop_reason = body.get("stop_reason")
    data = _parse_findings(text, stop_reason)
    return {
        "findings": data.get("findings") or [],
        "model": body.get("model") or REVIEW_MODEL,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


def review(pdf_bytes: bytes, job_release: str, model: str = None):
    """Return {findings, model, input_tokens, output_tokens}, or None on no key / any failure.

    `model` selects the reviewing model — a friendly alias ('sonnet' for a lighter/faster
    review, 'opus' for the deep one) or a raw model id; None uses the configured default.
    `findings` is a list of dicts (rule_id, issue, verdict, severity, computation,
    values_used, evidence, location). Empty list means Carmen reviewed and found nothing.
    """
    if not pdf_bytes or len(pdf_bytes) > MAX_PDF_BYTES:
        logger.info("bb_pdf_review_skipped", reason="empty or over size ceiling",
                    size=len(pdf_bytes) if pdf_bytes else 0)
        return None
    resolved = resolve_model(model)
    try:
        result = _call_anthropic(pdf_bytes, job_release, model=resolved)
    except Exception as e:  # noqa: BLE001 — any failure → no result; caller records the error
        logger.error("bb_pdf_review_failed", error=str(e), model=resolved, exc_info=True)
        return None
    logger.info("bb_pdf_review_complete", job_release=job_release, model=resolved,
                findings=len(result["findings"]),
                input_tokens=result.get("input_tokens"), output_tokens=result.get("output_tokens"))
    return result
