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

# Owner/job matching across a 20-job production meeting (also reused by learn.py's
# synthesis) — Opus by default; downgrade via env var if cost/latency ever matters.
MATCH_MODEL = os.environ.get("OWNER_MATCH_MODEL", "claude-opus-4-8")
FUZZY_ACCEPT = 0.6   # ≥60% of a job's distinctive tokens present in the to-do → accept
# Record-level matching (description-first). A to-do is matched to the record whose
# description/name best overlaps it; description is weighted 2× because the room talks
# scope ("roof access ladder"), not project names. ACCEPT is deliberately low — the agent
# commits a best guess (≥1 distinctive description token, or ≥2 name tokens) and the
# reviewer corrects drift. Internal/admin to-dos share no record tokens → score 0 → skipped.
DESC_WEIGHT, NAME_WEIGHT, BIAS_BOOST = 2.0, 1.0, 0.5
SCOPE_MIN = 2        # ≥2 distinctive scope tokens → link a concrete record
NAME_MIN = 2         # ≥2 distinctive project-name tokens → job-level determination (no link)
CONF_SCALE = 6.0     # raw score → 0..1 confidence (a strong scope match scores ~6)
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


def _learned_owner(job_number):
    """A reviewer-corrected owner learned for this job (ExtractionSignal 'owner_map'),
    resolved through the org gate. None when nothing has been learned for the job."""
    if not job_number:
        return None
    from app.models import ExtractionSignal
    sig = ExtractionSignal.query.filter_by(
        signal_type="owner_map", key=str(job_number), active=True).first()
    return resolve_name_to_user(sig.value) if sig and sig.value else None


def _meeting_bias(meeting):
    """Which record kind this meeting is mostly about, so matching leans the right way:
    Thursday standup = production (releases); Monday = drafting (submittals). Read from an
    explicit meeting_type hint when present, else inferred from the meeting day. A formal
    per-meeting ruleset will replace the weekday heuristic later."""
    mt = (getattr(meeting, "meeting_type", "") or "").lower()
    if "draft" in mt:
        return "submittal"
    if "production" in mt:
        return "release"
    dt = getattr(meeting, "occurred_at", None) or getattr(meeting, "created_at", None)
    wd = dt.weekday() if dt is not None else None
    if wd == 0:       # Monday → drafting
        return "submittal"
    if wd == 3:       # Thursday → production
        return "release"
    return "release"  # default: most meetings cover mostly releases


def build_record_candidates():
    """Every active release + open submittal as its OWN candidate (record-level), carrying
    description and name token sets. Matching is description-first, so the description is
    the primary signal and the project name only a weak cross-job tiebreaker."""
    cands = []
    for r in Releases.query.filter(Releases.is_archived.is_(False)).all():
        name = set(_tokens(_project_part(r.job_name)))
        cands.append({
            "kind": "release", "release_id": r.id, "job_number": str(r.job),
            "label": r.job_name or "", "description": r.description or "",
            # SCOPE = description minus the project name, so a name that leaks into the
            # description ("call off the lift at Banyan High Point") isn't counted as scope.
            "scope_tokens": set(_tokens(r.description or "")) - name,
            "name_tokens": name, "pm": r.pm,
        })
    for s in Submittals.query.filter(~Submittals.status.ilike("%closed%")).all():
        name = set(_tokens(_project_part(s.project_name or "")))
        cands.append({
            "kind": "submittal", "submittal_id": s.submittal_id,
            "job_number": s.project_number or "",
            "label": s.project_name or s.title or "", "description": s.title or "",
            "scope_tokens": set(_tokens(s.title or "")) - name,
            "name_tokens": name,
            "bic": s.ball_in_court, "sub_mgr": s.submittal_manager,
        })
    return cands


def _best_record(text, cands, bias):
    """Highest-scoring record for the to-do text. Returns (cand, score, scope_count,
    name_count). SCOPE = description minus project name (4+ char) — the room talks scope,
    so it's weighted over name and drives concrete record linking; NAME drives a softer
    job-level determination. Splitting them lets 'call off the lift at Banyan High Point'
    (name-only) tag the job without mis-linking a release."""
    tt = set(_tokens(text))
    if not tt:
        return None, 0.0, 0, 0
    best, best_score, best_scope, best_name = None, 0.0, 0, 0
    for c in cands:
        scope = tt & {t for t in c["scope_tokens"] if len(t) >= 4}
        name = tt & {t for t in c["name_tokens"] if len(t) >= 4}
        if not scope and not name:
            continue
        s = DESC_WEIGHT * len(scope) + NAME_WEIGHT * len(name) + (BIAS_BOOST if c["kind"] == bias else 0)
        if s > best_score:
            best, best_score, best_scope, best_name = c, s, len(scope), len(name)
    return best, best_score, best_scope, best_name


def _anchor(item, job_number, title, cands, bias, confidence):
    """Anchor a to-do to a job. The meeting type sets the KIND (Thu→release, Mon→submittal);
    the title's scope picks WHICH record. Link a concrete record only when the title shares
    scope with one — otherwise tag the job alone (a determination the reviewer can pin via
    the picker). Infers the owner when the extractor didn't name one."""
    sub = [c for c in cands if c["job_number"] == str(job_number)]
    if not sub:
        return
    pool = [c for c in sub if c["kind"] == bias] or sub
    best, _, scope_count, _ = _best_record(title, pool, bias)
    rec = best or pool[0]
    item.matched_job_number = rec.get("job_number") or None
    item.matched_job_name = _project_part(rec.get("label") or "")[:128] or None
    item.match_source = rec["kind"]
    item.confidence = round(float(confidence), 3)
    if best and scope_count >= 1:   # scope present → link the concrete record
        if best["kind"] == "release" and best.get("release_id") and not item.release_id:
            item.release_id = best["release_id"]
        if best["kind"] == "submittal" and best.get("submittal_id") and not item.submittal_id:
            item.submittal_id = best["submittal_id"]
    if not item.proposed_owner_user_id:
        owner = _learned_owner(rec.get("job_number")) or _candidate_owner(rec)
        if owner:
            item.proposed_owner_user_id, item.owner_inferred = owner, True


def _haiku_match(items, cands):
    """One batched Haiku call: map each to-do to a job_number (or null). Conservative —
    null is correct for out-of-system to-dos. Returns (list[(idx, job_number, conf)], usage)."""
    if not cfg.ANTHROPIC_API_KEY:
        return [], _zero_usage()
    jobs_map = {}  # record-level cands → one entry per job for the job-level LLM pass
    for c in cands:
        jn = c.get("job_number")
        if jn and jn not in jobs_map:
            jobs_map[jn] = c.get("label") or ""
    jobs = [{"job_number": jn, "name": nm} for jn, nm in jobs_map.items()]
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
            "content-type": "application/json"}, json=body, timeout=180)  # Opus-paced
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


def _backfill_match_tags(meeting):
    """Items the EXTRACTOR linked directly (release_ref/submittal_ref) carry a record id but
    no matched_* tags, so the badge wouldn't render. Fill the tags (and infer the owner if
    missing) from the linked record so the link and the badge always agree."""
    for it in meeting.items.all():
        if it.matched_job_name or not (it.release_id or it.submittal_id):
            continue
        if it.release_id:
            r = db.session.get(Releases, it.release_id)
            if not r:
                continue
            it.matched_job_number, it.match_source = str(r.job), "release"
            it.matched_job_name = _project_part(r.job_name or "")[:128] or None
            owner = _learned_owner(str(r.job)) or resolve_pm_initials(r.pm)
        else:
            s = db.session.get(Submittals, it.submittal_id)
            if not s:
                continue
            it.matched_job_number, it.match_source = (s.project_number or None), "submittal"
            it.matched_job_name = _project_part(s.project_name or s.title or "")[:128] or None
            owner = _learned_owner(s.project_number) or submittal_owner_user(s)
        if owner and not it.proposed_owner_user_id:
            it.proposed_owner_user_id, it.owner_inferred = owner, True


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
            "content-type": "application/json"}, json=body, timeout=180)  # Opus-paced
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
    """Anchor each UNLINKED to-do to its best record and infer the owner.

    Description-first and record-level: every active release / open submittal is a
    candidate, scored on description overlap with the to-do, biased toward the kind this
    meeting is about (Thu production → releases, Mon drafting → submittals). The agent
    commits a best guess (fuzzy → Haiku fallback) and the reviewer corrects drift — we'd
    rather make a determination than leave a real to-do unanchored. Items the extractor
    already linked are reconciled (badge ↔ link) but not re-matched. Returns LLM usage."""
    items = [i for i in meeting.items.all() if not i.release_id and not i.submittal_id]
    cands = build_record_candidates()
    bias = _meeting_bias(meeting)
    # Normalize learned garbled→canonical names before matching so a mangled project still
    # resolves up front (not only via the post-hoc title fix).
    from app.brain.meetings.context import apply_aliases

    # Fast path: a strong SCOPE match (≥2 description tokens) is committed locally and
    # record-linked via the meeting's preferred kind. Weaker/name-only and admin to-dos go
    # to the LLM, which judges whether they're real work (null) and picks the job if so.
    # Match on the TITLE (the action's subject), not the detail — the detail often mentions
    # related-but-secondary work ("call off the lift after the balcony rails install") that
    # would wrongly pull an equipment/admin to-do onto that release. A strong scope OR name
    # overlap anchors locally; the rest go to the LLM, which judges real-vs-admin (null).
    pending = []
    for it in (items if cands else []):
        title = apply_aliases(it.title or "")
        best, score, scope_count, name_count = _best_record(title, cands, bias)
        if best and (scope_count >= SCOPE_MIN or name_count >= NAME_MIN):
            _anchor(it, best["job_number"], title, cands, bias, min(1.0, score / CONF_SCALE))
        else:
            pending.append(it)

    usage = _zero_usage()
    if pending and cands:
        matches, usage = _haiku_match(pending, cands)
        for idx, jn, conf in matches:
            if 0 <= idx < len(pending):
                it = pending[idx]
                _anchor(it, jn, apply_aliases(it.title or ""), cands, bias, conf or 0.5)

    # Reconcile extractor-linked items so the badge shows, then fix garbled project names
    # in the titles of everything we anchored to a real record.
    _backfill_match_tags(meeting)
    matched = [i for i in meeting.items.all() if i.matched_job_name]
    usage = _sum_usage(usage, _haiku_correct_titles(matched))

    db.session.commit()
    logger.info("owner_inference", meeting_id=meeting.id, bias=bias,
                processed=len(items), matched=len(matched))
    return usage
