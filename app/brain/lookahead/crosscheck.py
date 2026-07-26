"""
@milehigh-header
schema_version: 1
purpose: The GC-lookahead cross-check engine. Given the MHMW metal activities parsed from a
  GC weekly lookahead (parser.metal_activities) plus our own releases + submittals for the
  job, match each GC need-date to the record that satisfies it and classify the gap:
  on-track, slipped, still-in-drafting (no release yet), or missing entirely. This is the
  automated form of docs/lookahead-cross-check.md — pure functions over dicts, so it runs
  the same on live DB rows or on test fixtures. Matching is building + scope based and
  intentionally transparent (each result carries its evidence) because the GC's activity
  names never match our record names verbatim.
exports:
  buildings_of(text), scope_of(text): the two matching primitives
  cross_check(activities, releases, submittals): list of per-activity result dicts
imports_from: [re, datetime]
imported_by: [app/brain/lookahead/service.py, tests]
invariants:
  - Read-only pure functions; no DB, no mutation.
  - "embed" and "anchor bolt" are one scope family (anchor bolts land in our embed/baseplate
    packages); "structural steel" is its own family.
"""
import re
from datetime import date

# Scope families. Anchor bolts ride with embeds/baseplates, so they share a family.
STEEL = "steel"
EMBED = "embed"

# Result statuses, worst → best (drives severity + ordering).
STATUS_NO_RECORD = "no_record"      # GC needs it; we have no release or submittal — the loud gap
STATUS_IN_DRAFTING = "in_drafting"  # no release yet, but an open DRR exists — on the board, not released
STATUS_SLIP = "slip"                # released, but our green date is later than the GC need date
STATUS_ON_TRACK = "on_track"        # released, our date meets the GC need
STATUS_COMPLETE = "complete"        # already installed/complete on our side

_SEVERITY = {
    STATUS_NO_RECORD: "high",
    STATUS_IN_DRAFTING: "high",
    STATUS_SLIP: "medium",          # escalated to high past _SLIP_HIGH_DAYS below
    STATUS_ON_TRACK: "ok",
    STATUS_COMPLETE: "ok",
}
_SLIP_HIGH_DAYS = 7

_BLD = re.compile(r"\bB(?:ld|uilding)\s*([A-D])(?:\s*-\s*([A-D]))?", re.IGNORECASE)


def buildings_of(text):
    """Set of building letters a record/activity references.

    'Bld C' -> {'C'}; 'Bld B-D' -> {'B','C','D'} (the combined-scope case); 'Building D' -> {'D'}.
    """
    out = set()
    for m in _BLD.finditer(text or ""):
        a = m.group(1).upper()
        b = m.group(2)
        if b:
            out.update(chr(x) for x in range(ord(a), ord(b.upper()) + 1))
        else:
            out.add(a)
    return out


def scope_of(text):
    """Coarse scope family for matching: EMBED (incl. anchor bolts/baseplates), STEEL, or None."""
    t = (text or "").lower()
    if "embed" in t or "anchor bolt" in t or "base plate" in t or "baseplate" in t:
        return EMBED
    if "structural steel" in t or "steel" in t:
        return STEEL
    return None


def _building_letter(activity):
    b = activity.get("building") or ""
    m = re.search(r"Building\s+([A-D])", b, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _release_is_complete(r):
    if r.get("is_complete") is not None:
        return bool(r["is_complete"])
    stage = (r.get("stage") or "").strip().lower()
    return (
        stage in ("complete", "install complete")
        or (r.get("job_comp") or "").strip().upper() == "X"
        or (r.get("invoiced") or "").strip().upper() == "X"
    )


def _match_release(letter, scope, releases):
    """Best release covering this building + scope, or None. Prefers active over complete
    only when both exist for the same cell (an active release is the live commitment)."""
    hits = []
    for r in releases:
        desc = r.get("description") or ""
        if scope_of(desc) == scope and letter in buildings_of(desc):
            hits.append(r)
    if not hits:
        return None
    # An active (not-yet-complete) release is the one whose date we hold against the GC.
    active = [r for r in hits if not _release_is_complete(r)]
    return (active or hits)[0]


def _match_open_drr(letter, scope, submittals):
    """An open Drafting Release Review for this cell — meaning it's still on the board."""
    for s in submittals:
        if (s.get("type") or "").strip().lower() != "drafting release review":
            continue
        if (s.get("status") or "").strip().lower() != "open":
            continue
        title = s.get("title") or ""
        if scope_of(title) == scope and letter in buildings_of(title):
            return s
    return None


def _our_date(release):
    return release.get("start_install") or release.get("comp_eta")


def cross_check(activities, releases, submittals):
    """Match each GC metal activity to our records and classify the gap.

    Returns one result dict per activity: the GC need, the matched record (if any), our
    date, the slip in days, a status, and a severity — every field traceable to its source.
    """
    results = []
    for a in activities:
        letter = _building_letter(a)
        scope = scope_of(a["task_name"])
        need = a.get("start")

        matched_kind = matched_ref = matched_label = our_date = None
        slip_days = None

        release = _match_release(letter, scope, releases) if letter and scope else None
        if release is not None:
            matched_kind = "release"
            matched_ref = release.get("release")
            matched_label = release.get("description")
            if _release_is_complete(release):
                status = STATUS_COMPLETE
            else:
                our_date = _our_date(release)
                if our_date and need:
                    slip_days = (our_date - need).days
                    status = STATUS_SLIP if slip_days > 0 else STATUS_ON_TRACK
                else:
                    status = STATUS_ON_TRACK
        else:
            drr = _match_open_drr(letter, scope, submittals) if letter and scope else None
            if drr is not None:
                matched_kind = "submittal"
                matched_ref = drr.get("rel")
                matched_label = drr.get("title")
                status = STATUS_IN_DRAFTING
            else:
                status = STATUS_NO_RECORD

        severity = _SEVERITY[status]
        if status == STATUS_SLIP and slip_days is not None and slip_days > _SLIP_HIGH_DAYS:
            severity = "high"

        results.append(
            {
                "wbs_id": a.get("wbs_id"),
                "building": a.get("building"),
                "scope": scope,
                "gc_task": a["task_name"],
                "gc_need": need,
                "gc_finish": a.get("finish"),
                "matched_kind": matched_kind,
                "matched_ref": matched_ref,
                "matched_label": matched_label,
                "our_date": our_date,
                "slip_days": slip_days,
                "status": status,
                "severity": severity,
            }
        )
    return results
