"""The BB lifecycle assistant — one grounded Anthropic call per turn.

No tool loop: the server has already assembled the lifecycle bundle deterministically, so
each turn is a single Messages API call with the bundle attached to the current user turn.
Follows the raw-``requests`` idiom (app/brain/meetings/extract.py). Sonnet 5, adaptive
thinking (default), effort "medium". Captures the Anthropic ``request-id`` + usage for the
spend ledger.
"""
import json
import time

import requests

from app.config import Config as cfg
from app.logging_config import get_logger

from . import pricing
from .lifecycle_prompt import build_system_prompt

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT_SECONDS = 120
# Keep the attached bundle from ballooning the request.
_MAX_BUNDLE_CHARS = 40000


def _headers(key: str) -> dict:
    return {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def _system_blocks() -> list:
    return [{
        "type": "text",
        "text": build_system_prompt(),
        "cache_control": {"type": "ephemeral"},
    }]


def _user_turn(user_text: str, bundle) -> str:
    if bundle is None:
        return user_text + "\n\n<lifecycle_data>none — no release or submittal has been named yet</lifecycle_data>"
    payload = json.dumps(bundle, ensure_ascii=False)
    if len(payload) > _MAX_BUNDLE_CHARS:
        # Drop older timeline entries first if the bundle is oversized.
        trimmed = dict(bundle)
        tl = trimmed.get("timeline", [])
        while tl and len(json.dumps({**trimmed, "timeline": tl}, ensure_ascii=False)) > _MAX_BUNDLE_CHARS:
            tl = tl[len(tl) // 4:]  # drop the oldest quarter
            if len(tl) <= 4:
                break
        trimmed["timeline"] = tl
        trimmed["timeline_note"] = "older events dropped to fit"
        payload = json.dumps(trimmed, ensure_ascii=False)
    return f"{user_text}\n\n<lifecycle_data>\n{payload}\n</lifecycle_data>"


def _post(messages: list, key: str):
    resp = requests.post(
        ANTHROPIC_URL,
        headers=_headers(key),
        json={
            "model": cfg.BB_CHAT_MODEL,
            "max_tokens": cfg.BB_CHAT_MAX_TOKENS,
            "output_config": {"effort": cfg.BB_CHAT_EFFORT},
            "system": _system_blocks(),
            "messages": messages,
        },
        timeout=_TIMEOUT_SECONDS,
    )
    request_id = resp.headers.get("request-id") or resp.headers.get("anthropic-request-id")
    resp.raise_for_status()
    return resp.json(), request_id


def _final_text(content: list) -> str:
    return "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()


def run_chat(history: list, user_text: str, bundle=None, user_id=None) -> dict:
    """Answer `user_text` grounded in `bundle` (the assembled lifecycle), given prior `history`.

    `history` is a list of {"role", "content"} text turns. Returns the answer + a metrics block.
    """
    key = cfg.ANTHROPIC_API_KEY
    if not key:
        return {
            "configured": False,
            "answer": "BB chat isn't configured yet (no Anthropic API key set on the server).",
            "metrics": {"model": "stub", "input_tokens": 0, "output_tokens": 0,
                        "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0,
                        "duration_ms": 0, "request_ids": []},
        }

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": _user_turn(user_text, bundle)})

    started = time.monotonic()
    try:
        body, request_id = _post(messages, key)
    except requests.RequestException as exc:
        logger.error("bb_chat_anthropic_error", error=str(exc),
                     error_type=type(exc).__name__, user_id=user_id, exc_info=True)
        raise

    duration_ms = int((time.monotonic() - started) * 1000)
    usage = pricing.usage_from_body(body, cfg.BB_CHAT_MODEL)
    answer = _final_text(body.get("content", []))
    if body.get("stop_reason") == "max_tokens":
        answer = (answer or "") + "\n\n(Response was cut off — ask me to continue.)"

    metrics = {
        "model": usage["model"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_write_tokens": usage["cache_write_tokens"],
        "cost_usd": usage["cost_usd"],
        "duration_ms": duration_ms,
        "request_ids": [request_id] if request_id else [],
    }
    # One wide event per turn, anchored on the Anthropic request-id for spend reconciliation.
    logger.info(
        "bb_chat_turn",
        user_id=user_id,
        model=metrics["model"],
        request_id=request_id,
        input_tokens=metrics["input_tokens"],
        output_tokens=metrics["output_tokens"],
        cache_read_tokens=metrics["cache_read_tokens"],
        cache_write_tokens=metrics["cache_write_tokens"],
        cost_usd=metrics["cost_usd"],
        duration_ms=duration_ms,
        grounded=bundle is not None,
    )
    return {"configured": True, "answer": answer or "(no answer)", "metrics": metrics}
