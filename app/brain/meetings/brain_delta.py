"""Drift detection: where the meeting's spoken reality diverges from the Brain.

READ-ONLY. This is the short-term step of the BB live-meeting roadmap (short = detect
drifts, medium = HITL review/apply, long = live in-meeting write-back). It never writes to
the job log / DWL — it only compares what was SAID against the current system-of-record
field values and records each mismatch as a BrainDrift the reviewer can see.

It SUBSUMES the v2 ChecklistItem.brain_update_pending flag: that only caught an
`agreed_change` the room committed to that never landed. This also catches a
`contradiction` — a plain status statement ("that canopy's at 25%") that disagrees with
the Brain (job_comp=20%) even though nobody "agreed to change" anything. The 480-625 miss
that motivated v3 was exactly a contradiction.

Like extract.py it uses the Anthropic Messages API when a key is set and degrades to NO
drifts (not a stub) on a missing key or any failure — drift detection without an LLM is
meaningless, and a $0/0-token usage marker signals it was skipped.
"""
import json
import re
from datetime import date, datetime

import requests

from app.config import Config as cfg
from app.logging_config import get_logger
from app.brain.meetings.extract import (
    ANTHROPIC_URL, EXTRACT_MODEL, MAX_TOTAL_CHARS, MAX_CONTEXT_CHARS, _usage,
)
from app.brain.meetings.snapshot import (
    RELEASE_FIELDS, SUBMITTAL_FIELDS, _parse_date, _to_float,
)

logger = get_logger(__name__)

VALID_KINDS = {"contradiction", "agreed_change"}


def _stub_usage() -> dict:
    """Zeroed usage marker when drift detection was skipped (no API / no entities)."""
    return {"input_tokens": 0, "output_tokens": 0, "model": "stub", "cost_usd": 0.0}


def _fmt(value) -> str:
    """Render a field value for the BRAIN STATE block (dates as ISO, None as '—')."""
    if value is None:
        return "—"
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)


def _brain_state_block(releases, submittals) -> str:
    """One line per entity with ALL its reconcilable field values — the authoritative
    'what the Brain holds right now' the transcript is compared against."""
    lines = []
    for r in releases:
        desc = (r.description or "").strip()
        desc = f' "{desc}"' if desc else ""
        fields = ", ".join(f"{f}={_fmt(getattr(r, f, None))}" for f in RELEASE_FIELDS)
        lines.append(f"- release {r.job}-{r.release} {r.job_name or ''}{desc} :: {fields}")
    for s in submittals:
        name = s.project_name or s.title or ""
        fields = ", ".join(f"{f}={_fmt(getattr(s, f, None))}" for f in SUBMITTAL_FIELDS)
        lines.append(f"- submittal {s.submittal_id} {name} :: {fields}")
    return "\n".join(lines)


def _system_prompt(today: date) -> str:
    return (
        "You are a precision auditor for Mile High Metal Works, a structural-steel "
        "fabricator. You compare what was SAID in a meeting against the BRAIN STATE (the "
        "job-log / DWL system of record) and report every DRIFT — each place a "
        "release/submittal field the room spoke about does NOT match what the Brain holds.\n"
        f"Today is {today.isoformat()} (America/Denver).\n"
        "You are given the BRAIN STATE (one line per release/submittal with its current "
        "field values, after '::') and then the TRANSCRIPT.\n\n"
        "A drift is any field where the room stated, implied, or agreed a value that "
        "differs from the Brain's current value. Two kinds:\n"
        "- \"contradiction\": the room reported a current status that disagrees with the "
        "Brain (e.g. \"that canopy's at 25%\" while the Brain shows job_comp=20%). Nobody "
        "needs to have agreed to change anything — a plain status statement that conflicts "
        "IS a drift, and the most important kind to catch.\n"
        "- \"agreed_change\": the room explicitly agreed a field should change to a new "
        "value (e.g. \"mark 480-146 shipped\", \"push install to next Friday\") and the "
        "Brain still shows the old value.\n\n"
        "Rules:\n"
        "- Only compare fields shown in the BRAIN STATE. Release fields: "
        + ", ".join(RELEASE_FIELDS) + ". Submittal fields: "
        + ", ".join(SUBMITTAL_FIELDS) + ".\n"
        "- Anchor every drift to ONE specific entity shown in the BRAIN STATE and put its "
        "EXACT token in `ref` (a release token like '480-625', or the submittal id). "
        "Resolve spoken scope phrases ('the P3 canopies', 'east stair') to the entity "
        "whose name/description matches. If you cannot confidently anchor a statement to a "
        "listed entity, DROP it — never invent a token or a value.\n"
        "- stated_value = what the room said (a date as YYYY-MM-DD, a percent like '25%', "
        "a stage name, a short string). brain_value = that entity's current value for the "
        "field, copied verbatim from the BRAIN STATE.\n"
        "- Report a field ONLY when the two genuinely differ. Treat dates as equal "
        "regardless of format; 'shipped' already satisfies a 'Ship Complete' stage; a bare "
        "'done' satisfies job_comp=X — do not report those as drifts.\n"
        "- quote = the short verbatim transcript span that states the value (<=200 chars).\n"
        "- confidence = 0..1 that this is a real drift worth the reviewer's time.\n"
        "- If nothing drifts, return an empty drifts array. A false drift wastes the "
        "reviewer's time — be conservative.\n"
        "Return STRICT JSON only — no prose, no markdown. Schema: "
        '{"drifts":[{"target":"release|submittal","ref":str,"field":str,'
        '"stated_value":str,"brain_value":str|null,"kind":"contradiction|agreed_change",'
        '"quote":str,"confidence":number}]}'
    )


def _build_user_content(brain_state: str, transcript: str) -> str:
    state = (brain_state or "").strip()[:MAX_CONTEXT_CHARS]
    head = f"=== BRAIN STATE (current job-log / DWL field values) ===\n{state}"
    transcript_budget = MAX_TOTAL_CHARS - len(head)
    return f"{head}\n\n=== TRANSCRIPT ===\n{(transcript or '')[:transcript_budget]}"


def _call_anthropic(transcript, releases, submittals, today):
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
            "max_tokens": 8000,
            "system": _system_prompt(today),
            "messages": [{"role": "user", "content": _build_user_content(
                _brain_state_block(releases, submittals), transcript)}],
        },
        timeout=480,  # background thread; Opus emits slowly on a long transcript
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("stop_reason") == "max_tokens":
        logger.warning("brain_delta_truncated", model=EXTRACT_MODEL)
    text = "".join(b.get("text", "") for b in body.get("content", []))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(m.group(0) if m else text)
    drifts = data.get("drifts", [])
    if not isinstance(drifts, list):
        raise ValueError("drifts is not a list")
    return drifts, _usage(body)


def detect_drifts(meeting, today: date = None) -> dict:
    """Return {'drifts': [...raw...], 'usage': {...}}. Never raises.

    Reuses the meeting's relevant-entities scoping so it sees the same releases/submittals
    the extraction context does (now additive + release-aware, so a specifically-named
    release is in scope). On a missing key, no entities, or any failure → no drifts with a
    zeroed usage marker, leaving the rest of extraction untouched.
    """
    from app.brain.meetings import context as meeting_context
    today = today or date.today()
    if not (meeting.transcript or "").strip():
        return {"drifts": [], "usage": _stub_usage()}
    try:
        releases, submittals = meeting_context.relevant_entities(meeting)
    except Exception as e:  # noqa: BLE001 — scoping must never break the caller
        logger.warning("brain_delta_scope_failed", meeting_id=meeting.id, error=str(e))
        return {"drifts": [], "usage": _stub_usage()}
    if not releases and not submittals:
        return {"drifts": [], "usage": _stub_usage()}
    try:
        drifts, usage = _call_anthropic(meeting.transcript, releases, submittals, today)
        logger.info("brain_delta_done", meeting_id=meeting.id, drifts=len(drifts))
        return {"drifts": drifts, "usage": usage}
    except Exception as e:  # noqa: BLE001 — any failure → no drifts (never the stub's guess)
        logger.info("brain_delta_fallback", meeting_id=meeting.id, error=str(e))
        return {"drifts": [], "usage": _stub_usage()}


def _is_noop(stated, brain):
    """True when the stated value doesn't actually differ from the Brain value.

    The model occasionally emits a 'drift' whose two values are identical (seen on real
    data: start_install '2026-07-06' vs '2026-07-06', job_comp 'X' vs 'X', both at low
    confidence). Those are no-ops, not drifts. Strict equality only — equal as dates, as
    numbers, or case-insensitively — NO containment, so a real '2%' vs '20%' is never
    suppressed."""
    if stated is None or brain is None:
        return False
    s, b = str(stated).strip(), str(brain).strip()
    if not s or not b:
        return False
    if s.lower() == b.lower():
        return True
    ds, db_ = _parse_date(s), _parse_date(b)
    if ds and db_:
        return ds == db_
    fs, fb = _to_float(s), _to_float(b)
    if fs is not None and fb is not None:
        return fs == fb
    return False


def sanitize_drift(raw):
    """Normalize one LLM-supplied drift into a stored dict, or None.

    Drops anything missing a target/field/ref, naming a field outside the allowlist for
    its target, or whose stated value doesn't actually differ from the Brain value — so a
    hallucinated field, an unanchored statement, or a no-op never persists."""
    if not isinstance(raw, dict):
        return None
    target = (raw.get("target") or "").strip().lower()
    field = (raw.get("field") or "").strip().lower()
    ref = (str(raw.get("ref") or "")).strip()
    if not ref or not field:
        return None
    allowed = {"release": RELEASE_FIELDS, "submittal": SUBMITTAL_FIELDS}.get(target, ())
    if field not in allowed:
        return None
    # The model sometimes reports a "drift" whose stated value equals the Brain value.
    if _is_noop(raw.get("stated_value"), raw.get("brain_value")):
        return None
    kind = (raw.get("kind") or "contradiction").strip().lower()
    if kind not in VALID_KINDS:
        kind = "contradiction"
    conf = raw.get("confidence")
    try:
        conf = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    return {
        "target": target,
        "ref": ref[:64],
        "field": field,
        "stated_value": _trim(raw.get("stated_value")),
        "brain_value": _trim(raw.get("brain_value")),
        "kind": kind,
        "quote": (str(raw.get("quote")).strip()[:2000] if raw.get("quote") else None),
        "confidence": conf,
    }


def _trim(v):
    return str(v).strip()[:255] if v is not None else None
