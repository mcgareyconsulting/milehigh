"""Generate a meeting summary from the transcript + the events that landed during it.

The second of a meeting's two outputs (the to-do checklist is the first). Where extraction
is grounded by the agenda, the summary is grounded by the "events context" — the
release/submittal updates that occurred during the meeting window (see
context.build_runtime_events) — woven together with the transcript narrative.

Same posture as extract.py: uses the Anthropic Messages API when a key is set; on a missing
key or ANY failure it falls back to a deterministic stub so the feature always works and
tests stay hermetic. Reuses extract.py's pricing/usage helpers so cost surfaces the same way.
"""
import os

import requests

from app.config import Config as cfg
from app.logging_config import get_logger
from app.brain.meetings.extract import ANTHROPIC_URL, _usage, _stub_usage

logger = get_logger(__name__)

# Multi-job production meetings need real synthesis across agenda + events + transcript;
# Opus by default (~$0.50/meeting) — downgrade via env var if cost/latency ever matters.
SUMMARY_MODEL = os.environ.get("MEETING_SUMMARY_MODEL", "claude-opus-4-8")

MAX_TOTAL_CHARS = 150000
MAX_EVENTS_CHARS = 8000     # the events block is the primary grounding; reserved first
MAX_AGENDA_CHARS = 30000    # fits a full production-meeting agenda; transcript keeps the room

_SYSTEM = (
    "You are an operations assistant for Mile High Metal Works, a structural-steel "
    "fabricator. Write a concise summary of an internal/GC meeting for a project manager "
    "who could not attend.\n"
    "You are given the TRANSCRIPT, an EVENTS DURING MEETING block — the release/submittal "
    "updates our systems recorded while the call was happening (stage moves, submittal "
    "approvals, ball-in-court changes, dates) — and possibly an AGENDA block: what the "
    "meeting was SUPPOSED to cover, often with per-job questions and urgency/status "
    "flags (e.g. OVERDUE, DUE TODAY, NEED CO).\n"
    "The agenda is the plan, not the meeting — NEVER restate or summarize the agenda "
    "itself; the reader already has it. Use it to judge what actually happened against "
    "what was planned, and to ground garbled job/release references to the canonical "
    "names and tokens it shows.\n"
    "Write 1–2 short paragraphs (or a few tight bullets): what was discussed and decided, who "
    "owes what, open risks — and explicitly fold in the system changes from the EVENTS block "
    "(e.g. 'during the call 480-146 moved to Fabrication'). Ground job references to the "
    "canonical tokens shown.\n"
    "If an AGENDA block is present, close with ONE line: 'Not addressed: …' listing any "
    "flagged agenda items the transcript never spoke to; omit the line entirely if "
    "everything flagged was covered.\n"
    "No preamble, no markdown headers — just the summary prose."
)


def _build_user_content(transcript: str, events: str, agenda: str = "") -> str:
    """Events (primary grounding) reserved first, agenda capped next, transcript gets the
    rest of the budget — a long agenda can squeeze the transcript but never the events."""
    ev = (events or "").strip()[:MAX_EVENTS_CHARS]
    ag = (agenda or "").strip()[:MAX_AGENDA_CHARS]
    head = f"=== EVENTS DURING MEETING ===\n{ev}\n\n" if ev else ""
    if ag:
        head += f"=== AGENDA (the plan — do not restate) ===\n{ag}\n\n"
    budget = MAX_TOTAL_CHARS - len(head)
    return f"{head}=== TRANSCRIPT ===\n{(transcript or '')[:budget]}"


def _call_anthropic(transcript: str, events: str, agenda: str = ""):
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
            "model": SUMMARY_MODEL,
            # A 20-job production meeting plus the 'Not addressed' line needs more room
            # than a single-project call; still asked to stay tight in the prompt.
            "max_tokens": 2000,
            "system": _SYSTEM,
            "messages": [{"role": "user",
                          "content": _build_user_content(transcript, events, agenda)}],
        },
        # ~40k tokens of input + Opus generation speed — 120s was Haiku-tuned and a
        # timeout silently degrades to the stub. Background thread, so be generous.
        timeout=300,
    )
    resp.raise_for_status()
    body = resp.json()
    text = "".join(b.get("text", "") for b in body.get("content", [])).strip()
    return text, _usage(body)


def _stub_summary(transcript: str, events: str) -> str:
    """Deterministic fallback: lead with the in-meeting system changes, then a transcript
    snippet, so a no-key environment still gets a useful, grounded digest."""
    parts = []
    ev = (events or "").strip()
    if ev:
        parts.append("Updates during the meeting:\n" + ev)
    body = (transcript or "").strip()
    if body:
        parts.append("Transcript excerpt:\n" + body[:1500])
    return "\n\n".join(parts)


def summarize(transcript: str, events: str = "", agenda: str = "") -> dict:
    """Return {'summary': str, 'usage': {input_tokens, output_tokens, model, cost_usd}}.

    `agenda` is the pre-meeting plan: used to judge what happened against what was planned
    (and close with a 'Not addressed' line), never summarized itself. An agenda alone
    produces no summary — there must be a transcript or in-meeting events.

    Never raises — on a missing key or any failure it falls back to the deterministic stub
    with zeroed usage (model='stub'), so a $0/0-token result signals the summary degraded.
    """
    if not (transcript or "").strip() and not (events or "").strip():
        return {"summary": "", "usage": _stub_usage()}
    try:
        text, usage = _call_anthropic(transcript, events, agenda)
        if text:
            return {"summary": text, "usage": usage}
        logger.info("meeting_summary_empty_llm_result")
    except Exception as e:  # noqa: BLE001 — any failure → deterministic stub
        logger.info("meeting_summary_fallback", error=str(e))
    return {"summary": _stub_summary(transcript, events), "usage": _stub_usage()}
