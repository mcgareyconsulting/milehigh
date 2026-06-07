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


def _system_prompt(today: date, people=None) -> str:
    roster = ""
    if people:
        roster = (
            "\nKnown team members — use these EXACT first names for owner_name when the "
            "responsible person is one of them: " + ", ".join(sorted(set(people))) + ".\n"
        )
    return (
        "You are an operations assistant for Mile High Metal Works, a structural-steel "
        "fabricator. You read transcripts of internal shop/drafting standups and GC "
        "(general contractor) coordination calls and extract a concrete, actionable "
        "to-do list a project manager can work straight from.\n"
        f"Today is {today.isoformat()} (America/Denver).\n"
        "Domain context: jobs flow through drafting → submittals (DRR/GC/FC approvals) → "
        "fabrication → paint → ship → install. People reference job-release tokens like "
        "'480-146', submittal numbers, ball-in-court, fab hours, and start-install dates.\n"
        + roster +
        "Extraction rules:\n"
        "- Capture every commitment, request, decision, risk, or needed follow-up — "
        "especially anything with an owner or a deadline.\n"
        "- Split compound asks into separate one-action items.\n"
        "- Write specific, verb-first titles (e.g. 'Send RFI 12 response to Turner for "
        "480-146'), not vague summaries ('discuss RFI').\n"
        "- owner_name = the FIRST NAME of whoever is responsible, if identifiable.\n"
        "- due_date = resolve relative dates (today, Thursday, EOW, 'by the 15th') to an "
        "absolute YYYY-MM-DD from today's date.\n"
        "- gc_facing = true when it involves a GC, owner, architect, or other external party.\n"
        "- release_ref = a job-release token like '480-146' if mentioned; submittal_ref = a "
        "submittal id/number if mentioned.\n"
        "- item_type: action (someone must do something), needs_gc_update (waiting on / must "
        "update a GC), decision (a choice that was made), risk (a problem or blocker), fyi "
        "(notable, no action).\n"
        "- confidence = 0..1 on how sure you are it is a real, actionable item.\n"
        "- Skip greetings, filler, and chit-chat. If nothing is actionable, return an empty "
        "items array.\n"
        "Return STRICT JSON only — no prose, no markdown. Schema: "
        '{"items":[{"title":str,"detail":str|null,'
        '"item_type":"action|needs_gc_update|decision|risk|fyi",'
        '"owner_name":str|null,"due_date":"YYYY-MM-DD"|null,"gc_facing":bool,'
        '"release_ref":str|null,"submittal_ref":str|null,"confidence":number}]}'
    )


def _call_anthropic(transcript: str, today: date, people=None) -> list:
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
            # A full standup transcript can yield 20-40 items; 2000 truncated the
            # JSON mid-array on real data and silently fell back to the keyword stub.
            "max_tokens": 8000,
            "system": _system_prompt(today, people),
            "messages": [{"role": "user", "content": transcript[:100000]}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    # Surface truncation loudly instead of letting a half-JSON fall through to the stub.
    if body.get("stop_reason") == "max_tokens":
        logger.warning("checklist_extract_truncated", model=EXTRACT_MODEL)
    text = "".join(b.get("text", "") for b in body.get("content", []))
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


def extract_items(transcript: str, today: date = None, people=None) -> list:
    """Return a list of proposed-item dicts. Never raises — falls back to the stub.

    `people` is an optional list of team first names; passed to the LLM so owner_name
    resolves to real users instead of guessed labels.
    """
    today = today or date.today()
    try:
        items = _call_anthropic(transcript, today, people)
        if items:
            return items
        logger.info("checklist_extract_empty_llm_result")
    except Exception as e:  # noqa: BLE001 — any failure → deterministic stub
        logger.info("checklist_extract_fallback", error=str(e))
    return _stub_extract(transcript)
