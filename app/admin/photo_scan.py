"""
@milehigh-header
schema_version: 1
purpose: Send an uploaded photo to AI vision models (Anthropic + OpenAI) to either parse a 3-/6-digit job code from it or locate a known code's bounding box, reporting per-provider time and cost. Research spike for feature/photo-mode-research.
exports:
  scan_with_anthropic / scan_with_openai: Parse a 3-/6-digit code from the image; uniform result dict
  locate_with_anthropic / locate_with_openai: Find a known code's normalized bounding box; uniform locate dict
  extract_code: Pull the first 3- or 6-digit code out of a model's text reply
imports_from: [requests, app.logging_config, flask]
imported_by: [app/admin/__init__.py]
invariants:
  - Public scan_*/locate_* helpers never raise: on missing key / HTTP / parse failure they return the uniform dict with `error` set, so one provider failing never breaks the other.
  - Pricing constants are hardcoded USD-per-token; update *_PRICE_* if model pricing changes.
  - locate_* boxes are normalized floats in [0,1] with (0,0) at the top-left, so the frontend can overlay them at any rendered size.
updated_by_agent: 2026-05-23T00:00:00Z
"""
import json
import re
import time

import requests
from flask import current_app

from app.logging_config import get_logger

logger = get_logger(__name__)

# --- Models -----------------------------------------------------------------
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o"

# --- Pricing (USD per token). Update if model pricing changes. --------------
# Anthropic Claude Sonnet 4.6: $3.00 / 1M input, $15.00 / 1M output.
ANTHROPIC_PRICE_IN = 3.00 / 1_000_000
ANTHROPIC_PRICE_OUT = 15.00 / 1_000_000
# OpenAI gpt-4o: $2.50 / 1M input, $10.00 / 1M output.
OPENAI_PRICE_IN = 2.50 / 1_000_000
OPENAI_PRICE_OUT = 10.00 / 1_000_000

SCAN_PROMPT = (
    "This image contains a job code in the format XXX-YYY (three digits, a "
    "hyphen, then three digits, e.g. 482-913). Reply with ONLY that code and "
    "nothing else. If no such code is visible, reply NONE."
)

LOCATE_PROMPT = (
    'The image contains a job code in the format XXX-YYY (three digits, a hyphen, '
    'three digits). Locate the exact text "{code}" in the image. Respond with '
    'ONLY a JSON object and nothing else, in this form: {{"found": true, "box": '
    '{{"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}}}}. Coordinates '
    'are normalized between 0 and 1, with (0,0) at the top-left corner, x '
    'increasing rightward and y downward, tightly bounding the code. If the code '
    'is not visible, respond {{"found": false}}.'
)

SCAN_MAX_TOKENS = 32      # we only want a number back
LOCATE_MAX_TOKENS = 200   # room for the JSON box
HTTP_TIMEOUT = 30  # seconds


# HEIC/HEIF ftyp brands. Neither vision API accepts these (iPhone default
# format), so we reject them up front with a clear message instead of firing
# two doomed API calls.
_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm",
                b"hevs", b"mif1", b"msf1")


def is_heic(data):
    """True if the bytes look like a HEIC/HEIF image (regardless of extension)."""
    return len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS


def extract_code(text):
    """Return a job code from `text` in canonical XXX-YYY form, else None.

    Prefers an explicit ``XXX-YYY`` match; falls back to a bare 6-digit run
    (reformatted with a hyphen, e.g. ``482913`` -> ``482-913``) in case OCR
    dropped the hyphen.
    """
    if not text:
        return None
    match = re.search(r"(?<!\d)\d{3}-\d{3}(?!\d)", text)
    if match:
        return match.group(0)
    match = re.search(r"(?<!\d)\d{6}(?!\d)", text)
    if match:
        digits = match.group(0)
        return f"{digits[:3]}-{digits[3:]}"
    return None


# --- Low-level provider calls ----------------------------------------------
# Each returns {error, text, input_tokens, output_tokens, cost_usd, elapsed_ms,
# model} and never raises. The scan_/locate_ helpers add their parsed field.

def _anthropic_vision(image_b64, media_type, prompt, max_tokens):
    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured", "text": None,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "elapsed_ms": 0.0, "model": ANTHROPIC_MODEL}

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": image_b64,
                }},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    start = time.perf_counter()
    try:
        resp = requests.post("https://api.anthropic.com/v1/messages",
                             json=payload, headers=headers, timeout=HTTP_TIMEOUT)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                    "text": None, "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "elapsed_ms": elapsed_ms, "model": ANTHROPIC_MODEL}
        data = resp.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        usage = data.get("usage", {})
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        cost = in_tok * ANTHROPIC_PRICE_IN + out_tok * ANTHROPIC_PRICE_OUT
        return {"error": None, "text": text, "input_tokens": in_tok,
                "output_tokens": out_tok, "cost_usd": cost,
                "elapsed_ms": elapsed_ms, "model": ANTHROPIC_MODEL}
    except Exception as exc:
        logger.error("anthropic vision call failed", error=str(exc))
        return {"error": str(exc), "text": None, "input_tokens": 0,
                "output_tokens": 0, "cost_usd": 0.0,
                "elapsed_ms": (time.perf_counter() - start) * 1000,
                "model": ANTHROPIC_MODEL}


def _openai_vision(image_b64, media_type, prompt, max_tokens):
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not configured", "text": None,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "elapsed_ms": 0.0, "model": OPENAI_MODEL}

    payload = {
        "model": OPENAI_MODEL,
        "max_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:{media_type};base64,{image_b64}",
                }},
            ],
        }],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start = time.perf_counter()
    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions",
                             json=payload, headers=headers, timeout=HTTP_TIMEOUT)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                    "text": None, "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "elapsed_ms": elapsed_ms, "model": OPENAI_MODEL}
        data = resp.json()
        text = (data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "") or "").strip()
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cost = in_tok * OPENAI_PRICE_IN + out_tok * OPENAI_PRICE_OUT
        return {"error": None, "text": text, "input_tokens": in_tok,
                "output_tokens": out_tok, "cost_usd": cost,
                "elapsed_ms": elapsed_ms, "model": OPENAI_MODEL}
    except Exception as exc:
        logger.error("openai vision call failed", error=str(exc))
        return {"error": str(exc), "text": None, "input_tokens": 0,
                "output_tokens": 0, "cost_usd": 0.0,
                "elapsed_ms": (time.perf_counter() - start) * 1000,
                "model": OPENAI_MODEL}


# --- Scan: parse the code out of the image ----------------------------------

def _scan_result(provider, res):
    return {
        "provider": provider,
        "model": res["model"],
        "code": extract_code(res["text"]),
        "raw_response": res["text"],
        "input_tokens": res["input_tokens"],
        "output_tokens": res["output_tokens"],
        "cost_usd": round(res["cost_usd"], 6),
        "elapsed_ms": round(res["elapsed_ms"], 1),
        "error": res["error"],
    }


def scan_with_anthropic(image_b64, media_type):
    return _scan_result("anthropic",
                        _anthropic_vision(image_b64, media_type, SCAN_PROMPT, SCAN_MAX_TOKENS))


def scan_with_openai(image_b64, media_type):
    return _scan_result("openai",
                        _openai_vision(image_b64, media_type, SCAN_PROMPT, SCAN_MAX_TOKENS))


# --- Locate: find a known code's bounding box -------------------------------

def _parse_box(text):
    """Pull a normalized {x_min,y_min,x_max,y_max} box out of a model JSON reply.

    Returns (found: bool, box: dict|None). Tolerates ```json fences and stray
    prose around the object. Returns (False, None) if unparseable.
    """
    if not text:
        return False, None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return False, None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return False, None
    if not data.get("found"):
        return False, None
    box = data.get("box") or {}
    try:
        coords = {k: float(box[k]) for k in ("x_min", "y_min", "x_max", "y_max")}
    except (KeyError, TypeError, ValueError):
        return False, None
    # Clamp to [0,1] so a slightly out-of-range guess still renders sanely.
    coords = {k: min(1.0, max(0.0, v)) for k, v in coords.items()}
    if coords["x_max"] <= coords["x_min"] or coords["y_max"] <= coords["y_min"]:
        return False, None
    return True, {k: round(v, 4) for k, v in coords.items()}


def _locate_result(provider, res):
    found, box = _parse_box(res["text"])
    return {
        "provider": provider,
        "model": res["model"],
        "found": found,
        "box": box,
        "raw_response": res["text"],
        "input_tokens": res["input_tokens"],
        "output_tokens": res["output_tokens"],
        "cost_usd": round(res["cost_usd"], 6),
        "elapsed_ms": round(res["elapsed_ms"], 1),
        "error": res["error"],
    }


def locate_with_anthropic(image_b64, media_type, target_code):
    prompt = LOCATE_PROMPT.format(code=target_code)
    return _locate_result("anthropic",
                          _anthropic_vision(image_b64, media_type, prompt, LOCATE_MAX_TOKENS))


def locate_with_openai(image_b64, media_type, target_code):
    prompt = LOCATE_PROMPT.format(code=target_code)
    return _locate_result("openai",
                          _openai_vision(image_b64, media_type, prompt, LOCATE_MAX_TOKENS))
