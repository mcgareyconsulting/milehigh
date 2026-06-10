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
EXTRACT_MODEL = os.environ.get("CHECKLIST_EXTRACT_MODEL", "claude-opus-4-8")
VALID_TYPES = {"action", "needs_gc_update", "decision", "risk", "fyi"}

# The whole user message (context + transcript) is kept under this char budget; context is
# capped first so it can never crowd out the transcript it's meant to ground. The context
# cap fits a full multi-job production-meeting agenda (~25k chars) with room for the job
# state + guidance sections; context.assemble_extraction_context budgets per-section
# against this same cap so a long agenda truncates itself, never the other sections.
MAX_TOTAL_CHARS = 150000
MAX_CONTEXT_CHARS = 40000

# USD per million tokens (input, output). Used to price each extraction so we can
# surface token + cost per meeting. Prefix match keeps dated model ids working.
MODEL_PRICING = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (1.0, 5.0),
}
_DEFAULT_PRICING = (15.0, 75.0)  # assume Opus if unknown — never under-report cost


def _price(model: str):
    for prefix, rates in MODEL_PRICING.items():
        if (model or "").startswith(prefix):
            return rates
    return _DEFAULT_PRICING


def _usage(body: dict) -> dict:
    """input/output tokens + computed USD cost from a Messages API response."""
    u = body.get("usage") or {}
    model = body.get("model") or EXTRACT_MODEL
    inp = int(u.get("input_tokens") or 0)
    out = int(u.get("output_tokens") or 0)
    pin, pout = _price(model)
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "model": model,
        "cost_usd": round(inp / 1e6 * pin + out / 1e6 * pout, 6),
    }


def _stub_usage() -> dict:
    """Zeroed usage marker when extraction fell back to the keyword stub (no API)."""
    return {"input_tokens": 0, "output_tokens": 0, "model": "stub", "cost_usd": 0.0}

_ACTION_HINTS = (
    "need", "redo", "today", "follow up", "follow-up", "asap", "by ", "send",
    "order", "confirm", "update", "fix", "schedule", "call", "make sure",
    "fab", "install", "submit", "release", "expedite", "deadline",
)


def _context_guidance(has_context: bool) -> str:
    if not has_context:
        return ""
    return (
        "\nThe user message has a CONTEXT block before the transcript, in delimited "
        "sections (PRE-MEETING CONTEXT, JOB STATE, LEARNED GUIDANCE). "
        "Use it as grounding, not as a source of new to-dos:\n"
        "- PRE-MEETING CONTEXT is the agenda/notes — use it to know what the meeting is about "
        "and to disambiguate vague references; explicit agenda asks may themselves be to-dos.\n"
        "- Ground vague references against the entities in JOB STATE (resolve 'Sand Creek' to "
        "the job shown, and use that job's CANONICAL name and release token in "
        "titles/release_ref).\n"
        "- Follow any LEARNED GUIDANCE about which kinds of items tend to be noise.\n"
        "- Structured agendas often pose explicit questions (e.g. 'Discussion Points', "
        "'shipped?', 'installed?') and carry urgency/status flags (e.g. OVERDUE, DUE TODAY, "
        "NEED CO — treat any similar marker the same way). Resolve them against the "
        "transcript:\n"
        "  - If the discussion reveals the system of record is stale (e.g. the agenda shows a "
        "release in Ship Planning but the room confirms it shipped), emit an action to make "
        "that exact update, citing the release token.\n"
        "  - If the room commits to an answer the agenda was waiting on (a date, a CO, a "
        "go/no-go), capture the commitment as an action with its owner and date.\n"
        "  - If a flagged agenda question is never addressed in the transcript, emit a "
        "follow-up action noting it was not covered in the meeting — use moderate "
        "confidence (0.4-0.6) since the room never spoke to it.\n"
        "- Only the TRANSCRIPT (and explicit agenda asks) are the source of to-dos; never invent "
        "items from the JOB STATE lines alone.\n"
    )


def _system_prompt(today: date, people=None, has_context: bool = False) -> str:
    roster = ""
    if people:
        roster = (
            "\nKnown team members (the ONLY valid owners) — set owner_name to one of these "
            "EXACT first names, and only when that person is clearly the one responsible: "
            + ", ".join(sorted(set(people))) + ".\n"
            "If the responsible person is not on this list, or you can't tell who it is, set "
            "owner_name to null. NEVER invent an owner or name someone who isn't listed — a "
            "wrong or out-of-org owner is worse than leaving it unassigned.\n"
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
        + roster + _context_guidance(has_context) +
        "Extraction rules:\n"
        "- Capture every commitment, request, decision, risk, or needed follow-up — "
        "especially anything with an owner or a deadline.\n"
        "- Split compound asks into separate one-action items.\n"
        "- Write specific, verb-first titles (e.g. 'Send RFI 12 response to Turner for "
        "480-146'), not vague summaries ('discuss RFI').\n"
        "- owner_name = the first name of whoever is responsible, but ONLY if they are a "
        "real team member (see the roster above); if not, or if unsure, use null — never "
        "guess or use a name that isn't a known team member.\n"
        "- due_date = resolve relative dates (today, Thursday, EOW, 'by the 15th') to an "
        "absolute YYYY-MM-DD from today's date.\n"
        "- gc_facing = true when it involves a GC, owner, architect, or other external party.\n"
        "- release_ref = a job-release token like '480-146' if mentioned; submittal_ref = a "
        "submittal id/number if mentioned.\n"
        "- Job-release codes are written XXX-YYY. If a bare six-digit number is used as a "
        "job/release reference (e.g. '170348'), hyphenate it as XXX-YYY ('170-348') "
        "everywhere it appears — in BOTH the title and release_ref.\n"
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


def _build_user_content(transcript: str, context=None) -> str:
    """Context block (capped) + the transcript, kept under the total char budget so the
    grounding context can never crowd out the transcript. No context → bare transcript."""
    ctx = (context or "").strip()
    if not ctx:
        return (transcript or "")[:MAX_TOTAL_CHARS]
    ctx = ctx[:MAX_CONTEXT_CHARS]
    transcript_budget = MAX_TOTAL_CHARS - len(ctx)
    return f"{ctx}\n\n=== TRANSCRIPT ===\n{(transcript or '')[:transcript_budget]}"


def _call_anthropic(transcript: str, today: date, people=None, context=None) -> list:
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
            # A multi-job production meeting with agenda coverage-gap items can double
            # that, so leave generous headroom — truncation = stub = garbage checklist.
            "max_tokens": 16000,
            "system": _system_prompt(today, people, has_context=bool((context or "").strip())),
            "messages": [{"role": "user", "content": _build_user_content(transcript, context)}],
        },
        # Opus emits ~50 tok/s; 10k+ output tokens takes minutes. This runs on a
        # background thread, so a long read is fine — a short one silently stubs.
        timeout=480,
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
    return items, _usage(body)


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


def extract(transcript: str, today: date = None, people=None, context=None) -> dict:
    """Return {'items': [...], 'usage': {input_tokens, output_tokens, model, cost_usd}}.

    Never raises — on a missing key or any failure it falls back to the deterministic
    keyword stub with zeroed usage (model='stub'), so a $0/0-token result is the visible
    signal that extraction degraded. `people` is an optional roster of team first names
    passed to the LLM so owner_name resolves to real users. `context` is an optional
    pre-meeting context block (agenda + current state/recent events + learned guidance)
    handed to the LLM as grounding alongside the transcript.
    """
    today = today or date.today()
    try:
        items, usage = _call_anthropic(transcript, today, people, context)
        if items:
            return {"items": items, "usage": usage}
        logger.info("checklist_extract_empty_llm_result")
    except Exception as e:  # noqa: BLE001 — any failure → deterministic stub
        logger.info("checklist_extract_fallback", error=str(e))
    return {"items": _stub_extract(transcript), "usage": _stub_usage()}


def extract_items(transcript: str, today: date = None, people=None) -> list:
    """Back-compat: items only (see `extract` for items + usage)."""
    return extract(transcript, today, people)["items"]
