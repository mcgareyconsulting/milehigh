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

# Summary is a cheap generative task — use Haiku by default (mirrors owner_match's matcher).
SUMMARY_MODEL = os.environ.get("MEETING_SUMMARY_MODEL", "claude-haiku-4-5-20251001")

MAX_TOTAL_CHARS = 100000
MAX_EVENTS_CHARS = 8000     # the events block is small; cap it so transcript keeps the room

_SYSTEM = (
    "You are an operations assistant for Mile High Metal Works, a structural-steel "
    "fabricator. Write a concise summary of an internal/GC meeting for a project manager "
    "who could not attend.\n"
    "You are given the TRANSCRIPT and an EVENTS DURING MEETING block — the release/submittal "
    "updates our systems recorded while the call was happening (stage moves, submittal "
    "approvals, ball-in-court changes, dates).\n"
    "Write 1–2 short paragraphs (or a few tight bullets): what was discussed and decided, who "
    "owes what, open risks — and explicitly fold in the system changes from the EVENTS block "
    "(e.g. 'during the call 480-146 moved to Fabrication'). Ground job references to the "
    "canonical tokens shown. No preamble, no markdown headers — just the summary prose."
)


def _build_user_content(transcript: str, events: str) -> str:
    ev = (events or "").strip()[:MAX_EVENTS_CHARS]
    head = f"=== EVENTS DURING MEETING ===\n{ev}\n\n" if ev else ""
    budget = MAX_TOTAL_CHARS - len(head)
    return f"{head}=== TRANSCRIPT ===\n{(transcript or '')[:budget]}"


def _call_anthropic(transcript: str, events: str):
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
            "max_tokens": 1200,
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": _build_user_content(transcript, events)}],
        },
        timeout=120,
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


def summarize(transcript: str, events: str = "") -> dict:
    """Return {'summary': str, 'usage': {input_tokens, output_tokens, model, cost_usd}}.

    Never raises — on a missing key or any failure it falls back to the deterministic stub
    with zeroed usage (model='stub'), so a $0/0-token result signals the summary degraded.
    """
    if not (transcript or "").strip() and not (events or "").strip():
        return {"summary": "", "usage": _stub_usage()}
    try:
        text, usage = _call_anthropic(transcript, events)
        if text:
            return {"summary": text, "usage": usage}
        logger.info("meeting_summary_empty_llm_result")
    except Exception as e:  # noqa: BLE001 — any failure → deterministic stub
        logger.info("meeting_summary_fallback", error=str(e))
    return {"summary": _stub_summary(transcript, events), "usage": _stub_usage()}
