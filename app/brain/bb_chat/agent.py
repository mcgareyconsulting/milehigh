"""The BB read-only tool-agent loop.

Manual Anthropic tool-use loop over the curated read-only tools in `tools.py` (ported from
the original banana_boy assistant). Raw `requests` (repo idiom), Sonnet 5, adaptive thinking
(default), effort "medium". Appends `response.content` verbatim each turn so thinking/tool_use
blocks replay correctly. Captures the Anthropic ``request-id`` + usage per call for the ledger.
"""
import json
import time

import requests

from app.config import Config as cfg
from app.logging_config import get_logger

from . import pricing, tools
from .lifecycle_prompt import build_system_prompt

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT_SECONDS = 120


def _headers(key: str) -> dict:
    return {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}


def _system_blocks(user) -> list:
    return [{"type": "text", "text": build_system_prompt(user), "cache_control": {"type": "ephemeral"}}]


def _post(messages: list, system: list, key: str):
    resp = requests.post(
        ANTHROPIC_URL,
        headers=_headers(key),
        json={
            "model": cfg.BB_CHAT_MODEL,
            "max_tokens": cfg.BB_CHAT_MAX_TOKENS,
            "output_config": {"effort": cfg.BB_CHAT_EFFORT},
            "system": system,
            "tools": tools.TOOL_DEFINITIONS,
            "messages": messages,
        },
        timeout=_TIMEOUT_SECONDS,
    )
    request_id = resp.headers.get("request-id") or resp.headers.get("anthropic-request-id")
    resp.raise_for_status()
    return resp.json(), request_id


def _final_text(content: list) -> str:
    return "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()


def run_chat(history: list, user_text: str, user=None, user_id=None) -> dict:
    """Answer `user_text` via the tool loop. `history` is prior {role, content} text turns."""
    key = cfg.ANTHROPIC_API_KEY
    if not key:
        return {
            "configured": False,
            "answer": "BB chat isn't configured yet (no Anthropic API key set on the server).",
            "metrics": {"model": "stub", "input_tokens": 0, "output_tokens": 0,
                        "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0,
                        "duration_ms": 0, "tool_calls": 0, "request_ids": []},
        }

    system = _system_blocks(user)
    tool_context = {"user_id": user_id}
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_text})

    totals, request_ids, tool_calls = {}, [], 0
    started = time.monotonic()
    answer = ""

    try:
        for _ in range(cfg.BB_CHAT_MAX_STEPS):
            body, request_id = _post(messages, system, key)
            if request_id:
                request_ids.append(request_id)
            pricing.accumulate(totals, pricing.usage_from_body(body, cfg.BB_CHAT_MODEL))

            content = body.get("content", [])
            messages.append({"role": "assistant", "content": content})
            tool_uses = [b for b in content if b.get("type") == "tool_use"]

            if body.get("stop_reason") == "tool_use" or tool_uses:
                results = []
                for b in tool_uses:
                    logger.info("bb_chat_tool_call", tool=b.get("name"), input=b.get("input"), user_id=user_id)
                    out = tools.execute_tool(b.get("name"), b.get("input") or {}, context=tool_context)
                    results.append({"type": "tool_result", "tool_use_id": b.get("id"),
                                    "content": json.dumps(out, default=str)})
                tool_calls += len(results)
                messages.append({"role": "user", "content": results})
                continue

            answer = _final_text(content)
            if body.get("stop_reason") == "max_tokens":
                answer = (answer or "") + "\n\n(Response was cut off — ask me to continue.)"
            break
        else:
            answer = "I couldn't finish that within the tool-call limit. Try narrowing the question."
    except requests.RequestException as exc:
        logger.error("bb_chat_anthropic_error", error=str(exc),
                     error_type=type(exc).__name__, user_id=user_id, exc_info=True)
        raise

    duration_ms = int((time.monotonic() - started) * 1000)
    metrics = {
        "model": totals.get("model", cfg.BB_CHAT_MODEL),
        "input_tokens": totals.get("input_tokens", 0),
        "output_tokens": totals.get("output_tokens", 0),
        "cache_read_tokens": totals.get("cache_read_tokens", 0),
        "cache_write_tokens": totals.get("cache_write_tokens", 0),
        "cost_usd": totals.get("cost_usd", 0.0),
        "duration_ms": duration_ms,
        "tool_calls": tool_calls,
        "request_ids": request_ids,
    }
    logger.info("bb_chat_turn", user_id=user_id, model=metrics["model"],
                request_id=request_ids[-1] if request_ids else None,
                input_tokens=metrics["input_tokens"], output_tokens=metrics["output_tokens"],
                cache_read_tokens=metrics["cache_read_tokens"], cache_write_tokens=metrics["cache_write_tokens"],
                cost_usd=metrics["cost_usd"], duration_ms=duration_ms, tool_calls=tool_calls)
    return {"configured": True, "answer": answer or "(no answer)", "metrics": metrics}
