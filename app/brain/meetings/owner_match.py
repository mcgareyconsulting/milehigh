"""Resolve a to-do's inferred owner from a matched release or submittal.

Owner sources (per MHMW rules):
  - Release  → the row's `pm` INITIALS (e.g. 'WO' / 'WDO' = Bill O'Neill) via PM_INITIALS.
  - Submittal → `ball_in_court` if it's a single name that resolves to an internal user;
               otherwise (multiple assignees, or external/unresolvable) `submittal_manager`.
  - `by` (drafter) is ignored.

Initials are FORMAL-first + last (William → W), so they can't be derived from the stored
nickname ("Bill"); the map is explicit. An unmapped initial yields NO owner — we never guess.

This module only does the entity → User resolution. The fuzzy/Haiku job matching that
picks WHICH release/submittal a to-do refers to lives in the inference pipeline.
"""
import json
import os
import re

import requests

from app.config import Config as cfg
from app.models import db, User, Releases, Submittals
from app.brain.meetings.extract import _usage as _llm_usage, ANTHROPIC_URL
from app.logging_config import get_logger

logger = get_logger(__name__)

MATCH_MODEL = os.environ.get("OWNER_MATCH_MODEL", "claude-haiku-4-5-20251001")
FUZZY_ACCEPT = 0.6   # ≥60% of a job's distinctive tokens present in the to-do → accept
_STOP = {"the", "and", "for", "to", "of", "on", "at", "in", "a", "an", "with", "by",
         "we", "need", "get", "this", "that"}

# Release `pm` initials → person's full name. Explicit because initials use the formal
# first name (WO/WDO = William "Bill" O'Neill). Extend here if a new PM appears.
PM_INITIALS = {
    "DR": "Danny Riddell",
    "RL": "Rich Losasso",
    "GA": "Gary Almeida",
    "WO": "Bill O'Neill",
    "WDO": "Bill O'Neill",
    "DS": "David Servold",
}


def _norm_initials(code):
    return re.sub(r"[^A-Za-z]", "", str(code or "")).upper()


def resolve_name_to_user(name):
    """Resolve a name (any order, with commas/apostrophes) to an ACTIVE User id.

    THE ORG GATE: this only ever returns the id of a current active employee, or None.
    A name that isn't a real team member, a garbled transcript token, or an ambiguous
    match (two people share the name) yields None — we infer when we can but never assign
    an owner who isn't in the org. All owner resolution (extracted names + inferred
    release PM / submittal ball-in-court) funnels through here so the gate is uniform.

    Tries progressively looser-but-still-unique matches: first+last → unique first name →
    unique last name. Uniqueness is required at every step so we never guess between two
    real users.
    """
    if not name:
        return None
    toks = {t.lower() for t in re.split(r"[\s,]+", str(name)) if t}
    if not toks:
        return None
    users = User.query.filter(User.is_active.is_(True)).all()
    # Prefer a first+last match.
    full = [u for u in users
            if u.first_name and u.last_name
            and u.first_name.lower() in toks and u.last_name.lower() in toks]
    if len(full) == 1:
        return full[0].id
    # Then a UNIQUE first-name match (ambiguous → give up rather than guess).
    first = [u for u in users if u.first_name and u.first_name.lower() in toks]
    if len(first) == 1:
        return first[0].id
    if len(first) > 1:
        return None
    # Last resort: a UNIQUE last-name match (e.g. transcript says only "Servold").
    last = [u for u in users if u.last_name and u.last_name.lower() in toks]
    return last[0].id if len(last) == 1 else None


def resolve_pm_initials(code):
    """Release pm/'WO' initials → active User id (via PM_INITIALS). None if unmapped or
    the mapped person isn't an active user."""
    name = PM_INITIALS.get(_norm_initials(code))
    return resolve_name_to_user(name) if name else None


def release_owner_user(release):
    """Owner for a release-matched to-do: the PM initials only."""
    return resolve_pm_initials(getattr(release, "pm", None))


def submittal_owner_user(submittal):
    """Owner for a submittal-matched to-do: single resolvable ball-in-court, else the
    submittal_manager. Multiple comma-separated BIC assignees skip straight to manager."""
    bic = (getattr(submittal, "ball_in_court", None) or "").strip()
    if bic and "," not in bic:
        uid = resolve_name_to_user(bic)
        if uid:
            return uid
    return resolve_name_to_user(getattr(submittal, "submittal_manager", None))


# --- Job matching (which release/submittal a to-do refers to) ----------------- #

def _tokens(s):
    return [t for t in re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()
            if len(t) >= 3 and t not in _STOP]


def _project_part(name):
    """Job names are often 'GC - Project'; the distinctive part is after the dash."""
    return name.split(" - ")[-1] if name and " - " in name else (name or "")


def _zero_usage():
    return {"input_tokens": 0, "output_tokens": 0, "model": None, "cost_usd": 0.0}


def build_candidates():
    """Active releases (one per job) + open submittals, as match candidates. Owner
    source fields are kept raw and resolved only for the candidate that actually wins."""
    cands, seen = [], set()
    for r in Releases.query.filter(Releases.is_archived.is_(False)).all():
        jn = str(r.job)
        if jn in seen:
            continue
        toks = set(_tokens(_project_part(r.job_name)))
        if not toks:
            continue
        seen.add(jn)
        cands.append({"kind": "release", "job_number": jn, "label": r.job_name,
                      "tokens": toks, "pm": r.pm})
    for s in Submittals.query.filter(~Submittals.status.ilike("%closed%")).all():
        toks = set(_tokens(_project_part(s.project_name or s.title or "")))
        if not toks:
            continue
        cands.append({"kind": "submittal", "job_number": s.project_number or "",
                      "label": s.project_name or s.title or "", "tokens": toks,
                      "bic": s.ball_in_court, "sub_mgr": s.submittal_manager,
                      "submittal_id": s.submittal_id})
    return cands


def _candidate_owner(c):
    if c["kind"] == "release":
        return resolve_pm_initials(c.get("pm"))
    bic = (c.get("bic") or "").strip()
    if bic and "," not in bic:
        uid = resolve_name_to_user(bic)
        if uid:
            return uid
    return resolve_name_to_user(c.get("sub_mgr"))


def _best_fuzzy(text, cands):
    """Best candidate by coverage of its distinctive tokens in the to-do text."""
    tt = set(_tokens(text))
    if not tt:
        return None, 0.0
    best, best_score = None, 0.0
    for c in cands:
        inter = tt & c["tokens"]
        if not inter or not any(len(t) >= 4 for t in inter):
            continue  # require ≥1 distinctive (4+ char) shared token
        score = len(inter) / len(c["tokens"]) + (0.001 if c["kind"] == "release" else 0)
        if score > best_score:
            best, best_score = c, score
    return best, min(best_score, 1.0)


def _haiku_match(items, cands):
    """One batched Haiku call: map each to-do to a job_number (or null). Conservative —
    null is correct for out-of-system to-dos. Returns (list[(idx, job_number, conf)], usage)."""
    if not cfg.ANTHROPIC_API_KEY:
        return [], _zero_usage()
    jobs = [{"job_number": c["job_number"], "name": c["label"]} for c in cands]
    todos = [{"i": i, "text": (it.title or "")[:160]} for i, it in enumerate(items)]
    system = (
        "You match a steel fabricator's internal meeting to-dos to its ACTIVE jobs. "
        "For each to-do, pick the job_number of the single best match, or null if no job "
        "clearly fits — many to-dos are internal/admin and match nothing, and null is the "
        "correct answer then. Be conservative. Return STRICT JSON only: "
        '{"matches":[{"i":int,"job_number":str|null,"confidence":number}]}'
    )
    body = {"model": MATCH_MODEL, "max_tokens": 4000, "system": system,
            "messages": [{"role": "user", "content": json.dumps({"jobs": jobs, "todos": todos})}]}
    try:
        resp = requests.post(ANTHROPIC_URL, headers={
            "x-api-key": cfg.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
            "content-type": "application/json"}, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        m = re.search(r"\{.*\}", text, re.DOTALL)
        matches = json.loads(m.group(0) if m else text).get("matches", [])
        out = [(int(x["i"]), x.get("job_number"), float(x.get("confidence") or 0.0))
               for x in matches if x.get("job_number")]
        return out, _llm_usage(data)
    except Exception as e:  # noqa: BLE001 — matching is best-effort
        logger.info("owner_match_haiku_failed", error=str(e))
        return [], _zero_usage()


def _apply(item, cand, confidence):
    """Tag the job + match confidence on the item; set the inferred owner if one resolves."""
    item.matched_job_number = (cand.get("job_number") or None)
    item.matched_job_name = _project_part(cand.get("label") or "")[:128] or None
    item.match_source = cand.get("kind")  # release | submittal
    item.confidence = round(float(confidence), 3)
    owner = _candidate_owner(cand)
    if owner:
        item.proposed_owner_user_id = owner
        item.owner_inferred = True
    if cand.get("submittal_id") and not item.submittal_id:
        item.submittal_id = cand["submittal_id"]


def _sum_usage(a, b):
    return {
        "input_tokens": (a.get("input_tokens") or 0) + (b.get("input_tokens") or 0),
        "output_tokens": (a.get("output_tokens") or 0) + (b.get("output_tokens") or 0),
        "model": a.get("model") or b.get("model"),
        "cost_usd": round((a.get("cost_usd") or 0) + (b.get("cost_usd") or 0), 6),
    }


def _haiku_correct_titles(items):
    """Fix ONLY the garbled job/project name in each matched to-do's title, using the
    canonical job name we matched it to (e.g. 'class of Sand Creek' → 'Sand Creek Flats').
    Everything else is kept verbatim. Returns aggregated usage."""
    if not cfg.ANTHROPIC_API_KEY or not items:
        return _zero_usage()
    payload = [{"i": i, "title": it.title, "job": it.matched_job_name}
               for i, it in enumerate(items)]
    system = (
        "Each to-do was matched to a known job. Fix ONLY the job/project NAME in the title "
        "to the canonical 'job' spelling — meeting transcripts garble names (e.g. 'class of "
        "Sand Creek' → 'Sand Creek Flats'). Keep the action, buildings, quantities and dates "
        "EXACTLY as written; change nothing but the job name, and only if it's wrong/garbled. "
        "If the title's name is already correct, return it unchanged. Return STRICT JSON only: "
        '{"titles":[{"i":int,"title":str}]}'
    )
    body = {"model": MATCH_MODEL, "max_tokens": 4000, "system": system,
            "messages": [{"role": "user", "content": json.dumps(payload)}]}
    try:
        resp = requests.post(ANTHROPIC_URL, headers={
            "x-api-key": cfg.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
            "content-type": "application/json"}, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        m = re.search(r"\{.*\}", text, re.DOTALL)
        for row in json.loads(m.group(0) if m else text).get("titles", []):
            i, new = row.get("i"), (row.get("title") or "").strip()
            if isinstance(i, int) and 0 <= i < len(items) and new and new != items[i].title:
                items[i].title = new[:1000]
                items[i].name_corrected = True
        return _llm_usage(data)
    except Exception as e:  # noqa: BLE001 — correction is best-effort
        logger.info("owner_match_correct_failed", error=str(e))
        return _zero_usage()


def infer_owners_for_meeting(meeting):
    """For the meeting's owner-less items, match to an active job (fuzzy → Haiku) and
    fill the inferred owner + job tag + match confidence. Returns aggregated Haiku usage
    so the caller can fold it into the meeting's cost meter."""
    items = [i for i in meeting.items.all() if not i.proposed_owner_user_id]
    if not items:
        return _zero_usage()
    cands = build_candidates()
    if not cands:
        return _zero_usage()

    pending = []
    for it in items:
        best, score = _best_fuzzy(f"{it.title or ''} {it.detail or ''}", cands)
        if best and score >= FUZZY_ACCEPT:
            _apply(it, best, score)
        else:
            pending.append(it)

    usage = _zero_usage()
    if pending:
        matches, usage = _haiku_match(pending, cands)
        by_job = {}
        for c in cands:  # prefer release over submittal for a given job_number
            if c["job_number"] and (c["job_number"] not in by_job or c["kind"] == "release"):
                by_job[c["job_number"]] = c
        for idx, jn, conf in matches:
            c = by_job.get(str(jn))
            if c and 0 <= idx < len(pending):
                _apply(pending[idx], c, conf)

    # Name-check: fix garbled job names in the titles we anchored to a real job. Only
    # touches matched items (we never "correct" a name we couldn't verify in the DB).
    matched = [i for i in items if i.matched_job_name]
    usage = _sum_usage(usage, _haiku_correct_titles(matched))

    db.session.commit()
    logger.info("owner_inference", meeting_id=meeting.id, unowned=len(items),
                matched=len(matched))
    return usage
