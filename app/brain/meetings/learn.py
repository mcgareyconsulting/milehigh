"""Learnings loop: what the agent learned once the human worked a meeting's checklist.

Runs after review (the yes/no/edit decisions are the signal). Two passes:

  Deterministic — facts read straight from the data, always captured:
    * owner_map signal when the reviewer reassigned an item off the proposed owner
    * accept/reject stats grouped by item_type and match_source (stored on the record)

  LLM (Haiku) — the qualitative synthesis the data can't give us:
    * a per-meeting summary + a breakdown keyed by the three dimensions
      (by_outcome / by_item_type / by_event)
    * reusable `alias` signals (garbled meeting name → canonical job name)
    * reusable `pattern` guidance keyed by item_type (e.g. "fyi items are usually noise")

Reusable signals land in ExtractionSignal (upsert + reinforce by count) so future
extractions read them back via app.brain.meetings.context. Best-effort/never-raises — on
a missing key or any LLM failure it still writes the deterministic learning (model='stub').
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from app.config import Config as cfg
from app.logging_config import get_logger
from app.models import db, Meeting, ChecklistItem, MeetingLearning, ExtractionSignal, User
from app.brain.meetings.extract import _usage as _llm_usage, ANTHROPIC_URL
from app.brain.meetings.owner_match import MATCH_MODEL

logger = get_logger(__name__)

# Learning is an LLM call, so it runs off-thread like extraction (web dyno has no scheduler).
_LEARN_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="meeting-learn")

_TRANSCRIPT_BUDGET = 40000
_CONTEXT_BUDGET = 8000


def start_learning(app, meeting_id):
    """Queue background learnings synthesis for a meeting."""
    _LEARN_POOL.submit(_run_learning_job, app, meeting_id)


def _run_learning_job(app, meeting_id):
    with app.app_context():
        try:
            meeting = db.session.get(Meeting, meeting_id)
            if meeting:
                synthesize_learnings(meeting)
        except Exception as e:  # noqa: BLE001 — record + log, never crash the worker
            logger.error("learn_job_failed", meeting_id=meeting_id, error=str(e), exc_info=True)
            db.session.rollback()
        finally:
            db.session.remove()


def _user_name(uid):
    if not uid:
        return None
    u = db.session.get(User, uid)
    return ChecklistItem._name(u) if u else None


def _build_labeled_items(meeting):
    """Proposed-vs-final picture per item — the labeled examples the agent learns from."""
    out = []
    for it in meeting.items.order_by(ChecklistItem.id).all():
        out.append({
            "id": it.id,
            "title": it.title,
            "item_type": it.item_type,
            "matched_job_number": it.matched_job_number,
            "matched_job_name": it.matched_job_name,
            "match_source": it.match_source,
            "name_corrected": bool(it.name_corrected),
            "status": it.status,                      # accepted | rejected | done | proposed
            "proposed_owner": _user_name(it.proposed_owner_user_id),
            "final_owner": _user_name(it.owner_user_id),
            "owner_changed": bool(it.owner_user_id
                                  and it.owner_user_id != it.proposed_owner_user_id),
            "due_changed": bool(it.due_date and it.due_date != it.proposed_due_date),
        })
    return out


def _stats(labeled):
    """Accept/reject tallies grouped by item_type and match_source (deterministic)."""
    def tally(key):
        acc = {}
        for r in labeled:
            k = r.get(key) or "unmatched"
            b = acc.setdefault(k, {"accepted": 0, "rejected": 0, "done": 0, "proposed": 0})
            b[r["status"]] = b.get(r["status"], 0) + 1
        return acc
    return {"by_item_type": tally("item_type"), "by_match_source": tally("match_source"),
            "total": len(labeled)}


# --- reusable signal upsert -------------------------------------------------- #

def upsert_signal(signal_type, key, value, source_meeting_id=None):
    """Create a signal or reinforce an existing one (bump count, refresh value)."""
    key = (key or "").strip()[:255]
    if not key or not (value or "").strip():
        return None
    sig = ExtractionSignal.query.filter_by(signal_type=signal_type, key=key).first()
    if sig:
        sig.count = (sig.count or 1) + 1
        sig.value = value
        sig.active = True
        sig.updated_at = datetime.utcnow()
    else:
        sig = ExtractionSignal(signal_type=signal_type, key=key, value=value,
                               count=1, active=True, source_meeting_id=source_meeting_id)
        db.session.add(sig)
    return sig


def _capture_owner_maps(meeting, labeled):
    """When the reviewer reassigned an item off the proposed owner on a matched job, learn
    that job → corrected-owner mapping so the same job defaults right next time."""
    n = 0
    for r in labeled:
        if (r["owner_changed"] and r["final_owner"] and r["matched_job_number"]
                and r["status"] in ("accepted", "done")):
            upsert_signal("owner_map", r["matched_job_number"], r["final_owner"], meeting.id)
            n += 1
    return n


# --- LLM synthesis ----------------------------------------------------------- #

_SYS = (
    "You analyze how a steel fabricator's meeting to-do extraction performed, AFTER a human "
    "reviewed the proposed items (accepted / rejected / edited). You are given the agenda, the "
    "transcript, a snapshot of relevant job state/recent events, and the per-item proposed-vs-"
    "final outcomes. Produce learnings that make the NEXT extraction better.\n"
    "Return STRICT JSON only:\n"
    '{"summary": str,'
    ' "by_outcome": {"accepted": str, "rejected": str, "edited": str},'
    ' "by_item_type": {"<type>": str},'
    ' "by_event": str,'
    ' "aliases": [{"from": str, "to": str}],'
    ' "patterns": [{"item_type": str, "guidance": str}]}\n'
    "- summary: 2-4 sentences on what this meeting taught us.\n"
    "- by_outcome: what the accepted vs rejected vs edited items had in common.\n"
    "- by_item_type: per item_type, a short note on how reliable that type was here.\n"
    "- by_event: how the recent-activity snapshot related to what was discussed.\n"
    "- aliases: ONLY garbled names the transcript used that map to a canonical job name shown "
    "in the state snapshot or matched job (from=garbled spelling, to=canonical). [] if none.\n"
    "- patterns: durable, reusable guidance (e.g. 'fyi items in internal standups are usually "
    "rejected'). Keep each under 140 chars. [] if nothing durable.\n"
    "Be conservative: empty arrays are correct when there's no real signal."
)


def _llm_synthesize(meeting, labeled, stats):
    """One Haiku call → (data_dict, usage). ({}, zero-usage) on no key / any failure."""
    zero = {"input_tokens": 0, "output_tokens": 0, "model": "stub", "cost_usd": 0.0}
    if not cfg.ANTHROPIC_API_KEY:
        return {}, zero
    payload = {
        "agenda": (meeting.agenda_text or "")[:_CONTEXT_BUDGET],
        "state_snapshot": (meeting.context_snapshot or "")[:_CONTEXT_BUDGET],
        "transcript": (meeting.transcript or "")[:_TRANSCRIPT_BUDGET],
        "items": labeled,
        "stats": stats,
    }
    body = {"model": MATCH_MODEL, "max_tokens": 2000, "system": _SYS,
            "messages": [{"role": "user", "content": json.dumps(payload)}]}
    try:
        resp = requests.post(ANTHROPIC_URL, headers={
            "x-api-key": cfg.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
            "content-type": "application/json"}, json=body, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0) if m else text), _llm_usage(data)
    except Exception as e:  # noqa: BLE001 — synthesis is best-effort
        logger.info("learn_synthesize_failed", meeting_id=meeting.id, error=str(e))
        return {}, zero


def synthesize_learnings(meeting):
    """Build the per-meeting learning + distill reusable signals. Returns the MeetingLearning."""
    labeled = _build_labeled_items(meeting)
    stats = _stats(labeled)

    # Deterministic feedback first (reliable regardless of the LLM).
    owner_maps = _capture_owner_maps(meeting, labeled)

    data, usage = _llm_synthesize(meeting, labeled, stats)

    # LLM-distilled reusable signals.
    alias_n = pattern_n = 0
    for a in (data.get("aliases") or []):
        frm, to = (a.get("from") or "").strip(), (a.get("to") or "").strip()
        if frm and to and frm.lower() != to.lower():
            upsert_signal("alias", frm, to, meeting.id)
            alias_n += 1
    for p in (data.get("patterns") or []):
        guidance = (p.get("guidance") or "").strip()
        itype = (p.get("item_type") or "any").strip()
        if guidance:
            upsert_signal("pattern", f"{itype}:{guidance[:80]}", guidance, meeting.id)
            pattern_n += 1

    payload = {
        "by_outcome": data.get("by_outcome"),
        "by_item_type": data.get("by_item_type"),
        "by_event": data.get("by_event"),
        "stats": stats,
    }
    learning = MeetingLearning(
        meeting_id=meeting.id,
        summary=(data.get("summary") or "").strip() or None,
        payload=payload,
        model=usage["model"],
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=usage["cost_usd"],
    )
    db.session.add(learning)
    meeting.learned_at = datetime.utcnow()
    db.session.commit()
    logger.info("meeting_learned", meeting_id=meeting.id, owner_maps=owner_maps,
                aliases=alias_n, patterns=pattern_n, model=usage["model"])
    return learning
