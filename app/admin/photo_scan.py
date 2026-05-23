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
GOOGLE_VISION_MODEL = "google-vision (DOCUMENT_TEXT_DETECTION)"
# Google Vision DOCUMENT_TEXT_DETECTION: ~$1.50 / 1000 images (flat per call,
# first 1000/month free). Reported as a flat per-request cost.
GOOGLE_VISION_PRICE_PER_IMAGE = 1.50 / 1000

# --- Pricing (USD per token). Update if model pricing changes. --------------
# Anthropic Claude Sonnet 4.6: $3.00 / 1M input, $15.00 / 1M output.
ANTHROPIC_PRICE_IN = 3.00 / 1_000_000
ANTHROPIC_PRICE_OUT = 15.00 / 1_000_000
# OpenAI gpt-4o: $2.50 / 1M input, $10.00 / 1M output.
OPENAI_PRICE_IN = 2.50 / 1_000_000
OPENAI_PRICE_OUT = 10.00 / 1_000_000

SCAN_PROMPT = (
    "This image contains a job code. It is either in the format XXX-YYY (three "
    "digits, a hyphen, three digits, e.g. 482-913) or a bare 3-digit stamp "
    "(e.g. 530). Reply with ONLY that code and nothing else. If no such code is "
    "visible, reply NONE."
)

LOCATE_PROMPT = (
    'Locate the exact text "{code}" (a job code or stamp) in the image. Respond '
    'with ONLY a JSON object and nothing else, in this form: {{"found": true, '
    '"box": {{"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}}}}. '
    'Coordinates are normalized between 0 and 1, with (0,0) at the top-left '
    'corner, x increasing rightward and y downward, tightly bounding the code. '
    'If the code is not visible, respond {{"found": false}}.'
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
    """Return a job code from `text`, else None.

    Tries, in order: an explicit ``XXX-YYY`` match; a bare 6-digit run
    (reformatted with a hyphen, e.g. ``482913`` -> ``482-913``) in case OCR
    dropped the hyphen; a bare 3-digit stamp (e.g. ``530``).
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
    match = re.search(r"(?<!\d)\d{3}(?!\d)", text)
    return match.group(0) if match else None


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
        "fallback": False,
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
        "fallback": False,
    }


def locate_with_anthropic(image_b64, media_type, target_code):
    prompt = LOCATE_PROMPT.format(code=target_code)
    return _locate_result("anthropic",
                          _anthropic_vision(image_b64, media_type, prompt, LOCATE_MAX_TOKENS))


def locate_with_openai(image_b64, media_type, target_code):
    prompt = LOCATE_PROMPT.format(code=target_code)
    return _locate_result("openai",
                          _openai_vision(image_b64, media_type, prompt, LOCATE_MAX_TOKENS))


# --- OCR locate: Google Vision returns pixel-accurate word boxes ------------

def _vertices_to_box(vertices):
    """Convert Google Vision boundingPoly vertices to (x_min,y_min,x_max,y_max) px.

    Vision omits the `x`/`y` key when the value is 0, so default to 0.
    """
    xs = [v.get("x", 0) for v in vertices]
    ys = [v.get("y", 0) for v in vertices]
    return min(xs), min(ys), max(xs), max(ys)


def _match_code_box(words, target_code):
    """Find `target_code` among OCR `words` and return its union pixel box.

    `words` is a list of (text, (x0,y0,x1,y1)). OCR may split the code across
    tokens ("290","-","153"), so we slide a 1-3 word window in reading order
    and match on hyphen-stripped digits. Returns (x0,y0,x1,y1) or None.
    """
    digits = target_code.replace("-", "")
    for size in (1, 2, 3):
        for i in range(len(words) - size + 1):
            window = words[i:i + size]
            joined = "".join(w[0] for w in window)
            if re.sub(r"\D", "", joined) == digits:
                xs0 = min(w[1][0] for w in window)
                ys0 = min(w[1][1] for w in window)
                xs1 = max(w[1][2] for w in window)
                ys1 = max(w[1][3] for w in window)
                return xs0, ys0, xs1, ys1
    return None


def _google_ocr(image_b64):
    """Run Google Vision DOCUMENT_TEXT_DETECTION. Never raises.

    Returns {error, full_text, words, width, height, elapsed_ms} where `words`
    is a list of (text, (x0,y0,x1,y1)) pixel boxes.
    """
    blank = {"error": None, "full_text": "", "words": [],
             "width": None, "height": None, "elapsed_ms": 0.0}
    api_key = current_app.config.get("GOOGLE_VISION_API_KEY")
    if not api_key:
        return {**blank, "error": "GOOGLE_VISION_API_KEY not configured"}

    payload = {"requests": [{
        "image": {"content": image_b64},
        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
    }]}

    start = time.perf_counter()
    try:
        resp = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            json=payload, timeout=HTTP_TIMEOUT)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return {**blank, "elapsed_ms": elapsed_ms,
                    "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
        result = (resp.json().get("responses") or [{}])[0]
        if result.get("error"):
            return {**blank, "elapsed_ms": elapsed_ms,
                    "error": str(result["error"].get("message", result["error"]))}

        annotations = result.get("textAnnotations") or []
        # annotations[0] is the whole-image text + box; [1:] are individual words.
        full_text = annotations[0]["description"].strip() if annotations else ""
        words = [(a.get("description", ""),
                  _vertices_to_box(a.get("boundingPoly", {}).get("vertices", [])))
                 for a in annotations[1:]]

        # Image dimensions for normalization (Vision returns them on the page).
        pages = (result.get("fullTextAnnotation") or {}).get("pages") or [{}]
        width = pages[0].get("width")
        height = pages[0].get("height")
        if (not width or not height) and annotations:
            # Fallback: the whole-image annotation box spans the image.
            _, _, width, height = _vertices_to_box(
                annotations[0].get("boundingPoly", {}).get("vertices", []))

        return {"error": None, "full_text": full_text, "words": words,
                "width": width, "height": height, "elapsed_ms": elapsed_ms}
    except Exception as exc:
        logger.error("google vision ocr failed", error=str(exc))
        return {**blank, "error": str(exc),
                "elapsed_ms": (time.perf_counter() - start) * 1000}


def scan_with_ocr(image_b64, media_type):
    """Read a code from the image via Google Vision OCR. Never raises."""
    ocr = _google_ocr(image_b64)
    return {
        "provider": "google",
        "model": GOOGLE_VISION_MODEL,
        "code": extract_code(ocr["full_text"]) if not ocr["error"] else None,
        "raw_response": (ocr["full_text"][:300] or None),
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0 if ocr["error"] else round(GOOGLE_VISION_PRICE_PER_IMAGE, 6),
        "elapsed_ms": round(ocr["elapsed_ms"], 1),
        "error": ocr["error"],
        "fallback": False,
    }


def locate_with_ocr(image_b64, media_type, target_code):
    """Locate a code via Google Vision OCR (pixel-accurate boxes). Never raises."""
    ocr = _google_ocr(image_b64)
    box = None
    if not ocr["error"]:
        px_box = _match_code_box(ocr["words"], target_code)
        if px_box and ocr["width"] and ocr["height"]:
            x0, y0, x1, y1 = px_box
            w, h = ocr["width"], ocr["height"]
            box = {
                "x_min": round(min(1.0, max(0.0, x0 / w)), 4),
                "y_min": round(min(1.0, max(0.0, y0 / h)), 4),
                "x_max": round(min(1.0, max(0.0, x1 / w)), 4),
                "y_max": round(min(1.0, max(0.0, y1 / h)), 4),
            }
    return {
        "provider": "google",
        "model": GOOGLE_VISION_MODEL,
        "found": box is not None,
        "box": box,
        "raw_response": (ocr["full_text"][:300] or None),
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0 if ocr["error"] else round(GOOGLE_VISION_PRICE_PER_IMAGE, 6),
        "elapsed_ms": round(ocr["elapsed_ms"], 1),
        "error": ocr["error"],
        "fallback": False,
    }


# --- Smart hybrid: OCR first, Sonnet fallback -------------------------------
# OCR nails printed/handwritten paper labels (precise + cheap) but reads nothing
# off stamped metal; the LLM is the inverse. Trying OCR first then falling back
# to the LLM covers both image types in one call.

def scan_smart(image_b64, media_type):
    ocr = scan_with_ocr(image_b64, media_type)
    if ocr["code"]:
        return ocr
    llm = scan_with_anthropic(image_b64, media_type)
    llm["fallback"] = True
    return llm


def locate_smart(image_b64, media_type, target_code):
    ocr = locate_with_ocr(image_b64, media_type, target_code)
    if ocr["found"]:
        return ocr
    llm = locate_with_anthropic(image_b64, media_type, target_code)
    llm["fallback"] = True
    return llm
