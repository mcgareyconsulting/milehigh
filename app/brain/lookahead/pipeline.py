"""
@milehigh-header
schema_version: 1
purpose: Read-only project pipeline pull for the GC-facing 3-week production lookahead.
  Loads every active release for a job plus open drafting (DRR) and open GC-approval
  submittals, with date-kind classification. Pure DB read; the schedule builder turns
  this into phase bars.
exports:
  get_project_pipeline(job_number): dict envelope {found, job, project_name, releases, drafting, gc_approvals, flags}
  classify_install_date(rel_like): hard | projected | asap | neutral | missing
imports_from: [app.models, app.api.helpers, app.logging_config]
imported_by: [app.brain.lookahead.schedule_builder, tests]
invariants:
  - Read-only. Never writes.
  - Active = not archived and is_active True/NULL (active_releases_filter).
  - All active work for the job is returned; window filtering is the builder's job.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.api.helpers import DEFAULT_FAB_ORDER, active_releases_filter
from app.logging_config import get_logger
from app.models import Releases, Submittals, is_gc_approval_type

logger = get_logger(__name__)

DRR_TYPE = "Drafting Release Review"

# date_kind values — mirror install_schedule.service classification.
KIND_HARD = "hard"
KIND_ASAP = "asap"
KIND_PROJECTED = "projected"
KIND_NEUTRAL = "neutral"
KIND_MISSING = "missing"

# Open-ish submittal statuses (case-insensitive). Closed/approved are excluded.
_CLOSED_STATUSES = frozenset({
    "closed", "approved", "void", "cancelled", "canceled", "rejected",
})


def _iso(d: Optional[date | datetime]) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat()


def _is_open_status(status: Optional[str]) -> bool:
    if not status or not str(status).strip():
        return True
    return str(status).strip().lower() not in _CLOSED_STATUSES


def classify_install_date(rel) -> str:
    """Label the install date the same way the install schedule / Timeline does."""
    start = getattr(rel, "start_install", None)
    if start is None and isinstance(rel, dict):
        start = rel.get("start_install")
    asap = getattr(rel, "start_install_asap", False)
    if isinstance(rel, dict):
        asap = rel.get("start_install_asap", False)
    no_color = getattr(rel, "start_install_no_color", False)
    if isinstance(rel, dict):
        no_color = rel.get("start_install_no_color", False)
    formula_tf = getattr(rel, "start_install_formulaTF", None)
    if isinstance(rel, dict):
        formula_tf = rel.get("start_install_formulaTF")

    if not start:
        return KIND_MISSING
    if asap:
        return KIND_ASAP
    if no_color:
        return KIND_NEUTRAL
    if formula_tf is False:
        return KIND_HARD
    return KIND_PROJECTED


def _release_is_complete(r: Releases) -> bool:
    stage = (r.stage or "").strip().lower()
    return (
        stage in ("complete", "install complete")
        or (r.job_comp or "").strip().upper() == "X"
        or (r.invoiced or "").strip().upper() == "X"
    )


def _release_row(r: Releases) -> dict[str, Any]:
    fab_order = r.fab_order
    unqueued = (
        fab_order is not None
        and abs(float(fab_order) - DEFAULT_FAB_ORDER) < 0.001
        and not _release_is_complete(r)
    )
    return {
        "kind": "release",
        "release_id": r.id,
        "job": r.job,
        "release": r.release,
        "code": f"{r.job}-{r.release}",
        "project_name": r.job_name,
        "description": r.description,
        "stage": r.stage,
        "stage_group": r.stage_group,
        "is_complete": _release_is_complete(r),
        "fab_hrs": r.fab_hrs,
        "install_hrs": r.install_hrs,
        "num_guys": r.num_guys,
        "fab_order": fab_order,
        "unqueued": unqueued,
        "paint_color": r.paint_color,
        "released": _iso(r.released),
        "start_install": _iso(r.start_install),
        "start_install_formulaTF": r.start_install_formulaTF,
        "start_install_asap": bool(r.start_install_asap),
        "start_install_no_color": bool(r.start_install_no_color),
        "date_kind": classify_install_date(r),
        "ship_date": _iso(r.ship_date),
        "comp_eta": _iso(r.comp_eta),
        "installer": r.installer,
        "pm": r.pm,
        "drafter": r.by,
        "job_comp": r.job_comp,
        "invoiced": r.invoiced,
        "notes": r.notes,
    }


def _drr_row(s: Submittals) -> dict[str, Any]:
    return {
        "kind": "drafting",
        "submittal_id": s.submittal_id,
        "project_number": s.project_number,
        "project_name": s.project_name,
        "title": s.title,
        "status": s.status,
        "type": s.type,
        "rel": s.rel,
        "code": f"{s.project_number}-DRR-{s.rel}" if s.rel is not None else f"DRR-{s.submittal_id}",
        "drafting_status": s.submittal_drafting_status,
        "ball_in_court": s.ball_in_court,
        "due_date": _iso(s.due_date),
        "start_install": _iso(s.start_install),
        "gc_jobsite_schedule_date": _iso(s.gc_jobsite_schedule_date),
        "created_at": _iso(s.created_at),
        "linked_release_id": s.linked_release_id,
        "link_status": s.link_status or "",
    }


def _gc_approval_row(s: Submittals) -> dict[str, Any]:
    return {
        "kind": "gc_approval",
        "submittal_id": s.submittal_id,
        "project_number": s.project_number,
        "project_name": s.project_name,
        "title": s.title,
        "status": s.status,
        "type": s.type,
        "ball_in_court": s.ball_in_court,
        "due_date": _iso(s.due_date),
        "created_at": _iso(s.created_at),
    }


def get_project_pipeline(job_number) -> dict[str, Any]:
    """Load all active production work for a job number.

    Returns a JSON-safe envelope. ``found`` is False when the job has no active
    releases and no open submittals under that number.
    """
    try:
        job_int = int(job_number)
    except (TypeError, ValueError):
        return {
            "found": False,
            "error": f"invalid job number: {job_number!r}",
            "job": None,
            "project_name": None,
            "releases": [],
            "drafting": [],
            "gc_approvals": [],
            "flags": [],
        }

    job_str = str(job_int)

    release_models = (
        Releases.query
        .filter(active_releases_filter(), Releases.job == job_int)
        .order_by(Releases.release.asc())
        .all()
    )

    submittals = (
        Submittals.query
        .filter(Submittals.project_number == job_str)
        .order_by(Submittals.last_updated.desc().nullslast())
        .all()
    )

    drafting = []
    gc_approvals = []
    for s in submittals:
        if not _is_open_status(s.status):
            continue
        if (s.type or "").strip() == DRR_TYPE:
            drafting.append(_drr_row(s))
        elif is_gc_approval_type(s.type):
            gc_approvals.append(_gc_approval_row(s))

    releases = [_release_row(r) for r in release_models]

    project_name = None
    if releases:
        project_name = releases[0].get("project_name")
    elif drafting:
        project_name = drafting[0].get("project_name")
    elif gc_approvals:
        project_name = gc_approvals[0].get("project_name")

    found = bool(releases or drafting or gc_approvals)

    # Pipeline-level flags (data quality, not schedule math).
    flags = []
    for r in releases:
        if r["unqueued"]:
            flags.append({
                "code": "unqueued",
                "severity": "medium",
                "release": r["code"],
                "message": f"{r['code']} is not sequenced in the shop queue yet.",
            })
        if r["date_kind"] == KIND_MISSING and not r["is_complete"]:
            flags.append({
                "code": "missing_install_date",
                "severity": "medium",
                "release": r["code"],
                "message": f"{r['code']} has no install date set.",
            })
    for d in drafting:
        if not d.get("due_date") and not d.get("start_install"):
            flags.append({
                "code": "unscheduled_drafting",
                "severity": "medium",
                "release": d["code"],
                "message": f"Drafting package '{d.get('title') or d['code']}' has no due or install date.",
            })

    logger.debug(
        "project_pipeline_loaded",
        job=job_int,
        release_count=len(releases),
        drafting_count=len(drafting),
        gc_approval_count=len(gc_approvals),
        found=found,
    )

    return {
        "found": found,
        "job": job_int,
        "project_name": project_name,
        "releases": releases,
        "drafting": drafting,
        "gc_approvals": gc_approvals,
        "flags": flags,
    }
