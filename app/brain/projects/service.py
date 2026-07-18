"""
@milehigh-header
schema_version: 1
purpose: Read-only rollup service for the Projects tab. Turns a `Projects` geofence row
  and its value-joined `Releases` / `Submittals` / event streams into the live payload
  the ProjectDetail modal renders (identity, releases, submittals, merged activity, and
  three computed health tiles). Financials/contract/customer sections have no backend
  source yet and are intentionally NOT produced here — the frontend keeps those on demo
  data with a "not yet wired" marker.
exports:
  list_projects(): list of {job_number, name, is_active, pm, release_count, submittal_count}
  get_project_live(job_number): full live payload for one project, or None if not found
imports_from: [datetime, sqlalchemy, app.models, app.api.helpers]
imported_by: [app/brain/projects/routes.py]
invariants:
  - Read-only. SELECTs only; never mutates.
  - Rollups are computed, never stored (percent_complete, health tiles, hours).
  - job_number is the natural key; Releases.job is int, Submittals.project_number is str.
"""
from datetime import date, datetime

from app.models import (
    Projects,
    Releases,
    Submittals,
    ReleaseEvents,
    SubmittalEvents,
    User,
)

# Canonical linear stage order (Released -> Complete). Progress % for a release is
# derived from where its stage sits on this line — the single production axis the
# client thinks in. "Hold" is handled separately (blocked, not a position).
STAGE_ORDER = [
    "Released",
    "Material Ordered",
    "Cut Start",
    "Cut Complete",
    "Fitup Start",
    "Fitup Complete",
    "Weld Start",
    "Weld Complete",
    "Welded QC",
    "Paint Start",
    "Paint Complete",
    "Store at MHMW",
    "Ship Planning",
    "Ship Complete",
    "Install Start",
    "Install Complete",
    "Complete",
]
_STAGE_INDEX = {s.lower(): i for i, s in enumerate(STAGE_ORDER)}

# Procore submittal statuses that mean the ball is no longer in play (closed out).
_CLOSED_SUBMITTAL_STATUSES = {"approved", "closed", "approved as noted", "for record only"}


def _pct_from_stage(stage):
    """Map a stage name to a 0-100 completion percent along the canonical line."""
    if not stage:
        return 0
    idx = _STAGE_INDEX.get(stage.strip().lower())
    if idx is None:
        return 0
    return round(idx / (len(STAGE_ORDER) - 1) * 100)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _hours(release):
    fab = release.fab_hrs or 0
    inst = release.install_hrs or 0
    total = fab + inst
    return round(total, 1) if total else 0


def _release_row(r):
    """Shape one Releases row for the Releases tab / progress rollup."""
    is_complete = (
        (r.stage or "").strip().lower() in ("complete", "install complete")
        or (r.job_comp or "").strip().upper() == "X"
        or (r.invoiced or "").strip().upper() == "X"
    )
    pct = 100 if is_complete else _pct_from_stage(r.stage)
    return {
        "release": r.release,
        "job_name": r.job_name,
        "description": r.description,
        "stage": r.stage or "Released",
        "stage_group": r.stage_group,
        "hours": _hours(r),
        "start_install": _iso(r.start_install),
        "pct": pct,
        "pm": r.pm,
        "installer": r.installer,
        "job_comp": r.job_comp,
        "invoiced": r.invoiced,
        "viewer_url": r.viewer_url,
        "is_blocked": (r.stage or "").strip().lower() == "hold",
    }


def _submittal_row(s):
    """Shape one Submittals row for the Submittals tab."""
    overdue = bool(
        s.due_date
        and s.due_date < date.today()
        and (s.status or "").strip().lower() not in _CLOSED_SUBMITTAL_STATUSES
    )
    return {
        "rel": s.rel,
        "title": s.title,
        "type": s.type,
        "status": s.status,
        "ball_in_court": s.ball_in_court,
        "submittal_manager": s.submittal_manager,
        "due_date": _iso(s.due_date),
        "overdue": overdue,
    }


# ---- activity feed --------------------------------------------------------

# Human-friendly verbs for the raw event `action` values.
_ACTION_LABEL = {
    "update_stage": "advanced the stage",
    "update_fab_order": "reordered fabrication",
    "update_notes": "updated notes",
    "update_start_install": "set the install date",
    "created": "created",
    "updated": "updated",
    "deleted": "deleted",
}


def _actor_names(internal_ids):
    """Resolve a set of user ids to display names in one query."""
    if not internal_ids:
        return {}
    rows = User.query.filter(User.id.in_(internal_ids)).all()
    out = {}
    for u in rows:
        name = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip()
        out[u.id] = name or u.username
    return out


def _event_text(action, payload):
    label = _ACTION_LABEL.get(action, action.replace("_", " "))
    # Surface a compact from->to when the payload carries it.
    if isinstance(payload, dict):
        frm = payload.get("from") or payload.get("from_stage") or payload.get("old")
        to = payload.get("to") or payload.get("to_stage") or payload.get("new")
        if frm is not None and to is not None:
            return f"{label}: {frm} → {to}"
    return label


def _activity_feed(job_number_int, submittal_ids, limit=40):
    """Merge release + submittal events for this project into one sorted feed."""
    rel_events = []
    if job_number_int is not None:
        rel_events = (
            ReleaseEvents.query.filter(
                ReleaseEvents.job == job_number_int,
                ReleaseEvents.is_system_echo.is_(False),
            )
            .order_by(ReleaseEvents.created_at.desc())
            .limit(limit)
            .all()
        )

    sub_events = []
    if submittal_ids:
        sub_events = (
            SubmittalEvents.query.filter(
                SubmittalEvents.submittal_id.in_([str(x) for x in submittal_ids]),
                SubmittalEvents.is_system_echo.is_(False),
            )
            .order_by(SubmittalEvents.created_at.desc())
            .limit(limit)
            .all()
        )

    actor_ids = {e.internal_user_id for e in rel_events if e.internal_user_id}
    actor_ids |= {e.internal_user_id for e in sub_events if e.internal_user_id}
    names = _actor_names(actor_ids)

    feed = []
    for e in rel_events:
        who = names.get(e.internal_user_id) or e.source or "System"
        feed.append(
            {
                "at": _iso(e.created_at),
                "_ts": e.created_at,
                "who": who,
                "text": f"{_event_text(e.action, e.payload)} on {e.release or e.job}",
                "kind": "release",
            }
        )
    for e in sub_events:
        who = names.get(e.internal_user_id) or e.source or "System"
        feed.append(
            {
                "at": _iso(e.created_at),
                "_ts": e.created_at,
                "who": who,
                "text": f"{_event_text(e.action, e.payload)} on submittal {e.submittal_id}",
                "kind": "submittal",
            }
        )

    feed.sort(key=lambda x: x["_ts"] or datetime.min, reverse=True)
    for item in feed:
        item.pop("_ts", None)
    return feed[:limit]


# ---- health tiles ---------------------------------------------------------

def _health_tiles(releases, submittals):
    """Three health signals with a real backend source. Each is a computed rollup."""
    today = date.today()

    overdue = sum(1 for s in submittals if s.get("overdue"))
    open_subs = sum(
        1 for s in submittals
        if (s.get("status") or "").strip().lower() not in _CLOSED_SUBMITTAL_STATUSES
    )

    # Install risk: releases whose install date is in the past but production isn't complete.
    at_risk = 0
    for r in releases:
        si = r.get("start_install")
        if si and r.get("pct", 0) < 100:
            try:
                if date.fromisoformat(si) < today:
                    at_risk += 1
            except ValueError:
                pass

    total = len(releases) or 1
    avg_pct = round(sum(r.get("pct", 0) for r in releases) / total)

    return [
        {
            "key": "submittals_overdue",
            "label": "Submittals Overdue",
            "value": f"{overdue}",
            "tone": "risk" if overdue else "good",
        },
        {
            "key": "installation_risk",
            "label": "Install Risk",
            "value": f"{at_risk}",
            "tone": "risk" if at_risk else "good",
        },
        {
            "key": "production_progress",
            "label": "Avg Production",
            "value": f"{avg_pct}%",
            "tone": "good" if avg_pct >= 80 else "warn" if avg_pct >= 40 else "neutral",
        },
        {
            "key": "open_submittals",
            "label": "Open Submittals",
            "value": f"{open_subs}",
            "tone": "neutral",
        },
        {
            "key": "release_count",
            "label": "Releases",
            "value": f"{len(releases)}",
            "tone": "neutral",
        },
    ]


# ---- public API -----------------------------------------------------------

def _job_number_as_int(job_number):
    try:
        return int(str(job_number).strip())
    except (TypeError, ValueError):
        return None


def list_projects():
    """Lightweight index: every project + its release/submittal counts and PM."""
    projects = Projects.query.order_by(Projects.job_number).all()
    out = []
    for p in projects:
        release_count = p.jobs.count()
        submittal_count = p.submittals.count()
        out.append(
            {
                "id": p.id,
                "job_number": p.job_number,
                "name": p.name,
                "is_active": p.is_active,
                "address": p.address,
                "pm": p.pm.name if p.pm else None,
                "pm_color": p.pm.color if p.pm else None,
                "release_count": release_count,
                "submittal_count": submittal_count,
            }
        )
    return out


def get_project_live(job_number):
    """Full live payload for one project, or None if no matching Projects row.

    Only the sections with a real backend source are populated: identity, releases,
    submittals, activity, and computed health. The caller (frontend) overlays these
    onto the demo scaffold for financials/contract/customer, which have no source yet.
    """
    project = Projects.query.filter(Projects.job_number == str(job_number)).first()
    if project is None:
        return None

    job_int = _job_number_as_int(project.job_number)

    # The model documents the value-join as cast(Projects.job_number, Integer) == Releases.job;
    # here job_int is that cast materialized, so we filter Releases.job directly.
    release_rows = (
        Releases.query.filter(Releases.job == job_int)
        .filter(Releases.is_active.isnot(False))
        .order_by(Releases.release)
        .all()
        if job_int is not None
        else []
    )
    submittal_models = (
        Submittals.query.filter(Submittals.project_number == project.job_number)
        .order_by(Submittals.order_number)
        .all()
    )

    releases = [_release_row(r) for r in release_rows]
    submittals = [_submittal_row(s) for s in submittal_models]

    percent_complete = (
        round(sum(r["pct"] for r in releases) / len(releases)) if releases else 0
    )

    activity = _activity_feed(
        job_int, [s.submittal_id for s in submittal_models]
    )

    return {
        "job_number": project.job_number,
        "name": project.name,
        "is_active": project.is_active,
        "address": project.address,
        "pm": project.pm.name if project.pm else None,
        "pm_color": project.pm.color if project.pm else None,
        "percent_complete": percent_complete,
        "releases": releases,
        "submittals": submittals,
        "activity": activity,
        "health": _health_tiles(releases, submittals),
        # Sections with no backend source yet — flagged so the UI can mark them.
        "unavailable_sections": ["financials", "contract", "customer", "contacts", "documents"],
    }
