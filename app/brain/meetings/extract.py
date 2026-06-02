"""Extract proposed checklist items from a meeting transcript.

Uses the Anthropic Messages API when ANTHROPIC_API_KEY is set; on a missing key or
ANY failure (bad model, network, malformed JSON) it falls back to a deterministic
keyword stub so the feature always works without a key — and tests stay hermetic.
Mirrors how Trello/Procore wrap raw `requests`.
"""
import json
import os
import re
from datetime import date

import requests

from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
EXTRACT_MODEL = os.environ.get("CHECKLIST_EXTRACT_MODEL", "claude-sonnet-4-6")
VALID_TYPES = {"action", "needs_gc_update", "decision", "risk", "fyi"}

_ACTION_HINTS = (
    "need", "redo", "today", "follow up", "follow-up", "asap", "by ", "send",
    "order", "confirm", "update", "fix", "schedule", "call", "make sure",
    "fab", "install", "submit", "release", "expedite", "deadline",
)


def _system_prompt(today: date) -> str:
    return (
        "You extract action items from a steel-fabrication company's internal or GC "
        "meeting transcript. Return STRICT JSON only — no prose, no markdown. "
        f"Today is {today.isoformat()}. Schema: "
        '{"items":[{"title":str,"detail":str|null,'
        '"item_type":"action|needs_gc_update|decision|risk|fyi",'
        '"owner_name":str|null,"due_date":"YYYY-MM-DD"|null,"gc_facing":bool,'
        '"release_ref":str|null,"submittal_ref":str|null,"confidence":number}]}. '
        "owner_name = first name of the responsible person if stated. "
        "due_date = resolve relative dates (today, Thursday, EOW) to absolute. "
        "release_ref = a job-release token like '480-146' if mentioned. "
        "Only include real action items / decisions / risks — skip chit-chat."
    )


def _call_anthropic(transcript: str, today: date) -> list:
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
            "max_tokens": 2000,
            "system": _system_prompt(today),
            "messages": [{"role": "user", "content": transcript[:100000]}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json().get("content", []))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(m.group(0) if m else text)
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("items is not a list")
    return items


def _stub_extract(transcript: str) -> list:
    """Deterministic fallback: one item per line that looks like an action."""
    items = []
    for line in (transcript or "").splitlines():
        s = line.strip().lstrip("-*•").strip()
        if len(s) < 6:
            continue
        low = s.lower()
        if any(h in low for h in _ACTION_HINTS):
            mref = re.search(r"\b(\d{2,4})-(\w+)\b", s)
            items.append({
                "title": s[:200],
                "detail": None,
                "item_type": "action",
                "owner_name": None,
                "due_date": None,
                "gc_facing": ("gc" in low or "client" in low),
                "release_ref": mref.group(0) if mref else None,
                "submittal_ref": None,
                "confidence": None,
            })
    return items


def extract_items(transcript: str, today: date = None) -> list:
    """Return a list of proposed-item dicts. Never raises — falls back to the stub."""
    today = today or date.today()
    try:
        items = _call_anthropic(transcript, today)
        if items:
            return items
        logger.info("checklist_extract_empty_llm_result")
    except Exception as e:  # noqa: BLE001 — any failure → deterministic stub
        logger.info("checklist_extract_fallback", error=str(e))
    return _stub_extract(transcript)
