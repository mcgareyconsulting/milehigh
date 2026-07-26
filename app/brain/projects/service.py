"""
@milehigh-header
schema_version: 1
purpose: Read-only rollup service for the Projects tab. Turns a `Projects` geofence row
  and its value-joined `Releases` / `Submittals` / event streams into the live payload
  the ProjectDetail modal renders (identity, releases, submittals, merged activity, a set
  of computed health tiles, and a composite 0-100 health SCORE). The score is the
  lookahead cross-check (docs/lookahead-cross-check.md) run automatically: start at 100
  and subtract a capped, itemized penalty per gap signal. Financials/contract/customer
  sections have no backend source yet and are intentionally NOT produced here — the
  frontend keeps those on demo data with a "not yet wired" marker.
exports:
  list_projects(): index rows + counts, PM, computed health_score band, and upcoming dates
  get_project_live(job_number): full live payload for one project, or None if not found
imports_from: [datetime, app.models, app.api.helpers]
imported_by: [app/brain/projects/routes.py]
invariants:
  - Read-only. SELECTs only; never mutates.
  - Rollups are computed, never stored (percent_complete, health tiles, health_score).
  - job_number is the natural key; Releases.job is int, Submittals.project_number is str.
"""
import re
from datetime import date, datetime, timedelta

from app.api.helpers import DEFAULT_FAB_ORDER
from app.brain.lookahead import service as lookahead_service
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
    """Shape one Releases row for the Releases tab / progress + health rollups."""
    is_complete = (
        (r.stage or "").strip().lower() in ("complete", "install complete")
        or (r.job_comp or "").strip().upper() == "X"
        or (r.invoiced or "").strip().upper() == "X"
    )
    pct = 100 if is_complete else _pct_from_stage(r.stage)

    # Install-at-risk: scheduled to install in the past but production isn't finished.
    at_risk = bool(
        not is_complete
        and r.start_install is not None
        and r.start_install < date.today()
    )
    # Unsequenced fab: a released item still sitting on the DEFAULT_FAB_ORDER placeholder
    # (never given a shop-queue position) yet with a real install date — the exact
    # "ready but not queued" gap the lookahead playbook flags.
    unsequenced = bool(
        not is_complete
        and r.fab_order is not None
        and abs(r.fab_order - DEFAULT_FAB_ORDER) < 1e-6
        and r.start_install is not None
    )

    return {
        "release": r.release,
        "job_name": r.job_name,
        "description": r.description,
        "stage": r.stage or "Released",
        "stage_group": r.stage_group,
        "hours": _hours(r),
        "start_install": _iso(r.start_install),
        "ship_date": _iso(r.ship_date),
        "fab_order": r.fab_order,
        "pct": pct,
        "pm": r.pm,
        "installer": r.installer,
        "job_comp": r.job_comp,
        "invoiced": r.invoiced,
        "viewer_url": r.viewer_url,
        "is_blocked": (r.stage or "").strip().lower() == "hold",
        "at_risk": at_risk,
        "unsequenced": unsequenced,
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
    """The health signals with a real backend source. Each is a computed rollup and
    doubles as the drill-down detail behind the composite health_score."""
    overdue = sum(1 for s in submittals if s.get("overdue"))
    open_subs = sum(
        1 for s in submittals
        if (s.get("status") or "").strip().lower() not in _CLOSED_SUBMITTAL_STATUSES
    )
    at_risk = sum(1 for r in releases if r.get("at_risk"))
    unsequenced = sum(1 for r in releases if r.get("unsequenced"))

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
            "key": "unsequenced_fab",
            "label": "Unsequenced Fab",
            "value": f"{unsequenced}",
            "tone": "risk" if unsequenced else "good",
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


# ---- health score ---------------------------------------------------------

# Composite 0-100 project-health score. Start at 100, subtract a capped penalty per
# lookahead gap signal (docs/lookahead-cross-check.md), and return each deduction with
# its evidence count so the number is never a mystery. The weights below are the single
# tunable knob — (key, points_each, cap).
SCORE_RUBRIC = [
    ("install_at_risk", 10, 30),
    ("unsequenced_fab", 10, 20),
    ("overdue_submittal", 8, 24),
    ("stale_drr", 6, 18),
]

# Score band cutoffs. >=85 green, 65-84 amber, <65 red.
_GREEN_MIN = 85
_AMBER_MIN = 65

# GC-lookahead deductions — only fire when a lookahead cross-check is present. These are the
# external-benchmark signals the internal rubric structurally can't see (does our schedule
# meet the GC's need dates?). Points by cross-check status; a slip escalates past a week.
_LOOKAHEAD_POINTS = {"no_record": 25, "in_drafting": 20, "slip": 6}
_LOOKAHEAD_SLIP_HIGH_DAYS = 7
_LOOKAHEAD_SLIP_HIGH_POINTS = 12

# Human scope labels for lookahead deduction reasons.
_SCOPE_LABEL = {"steel": "structural steel", "embed": "embeds"}


def _short_building(building):
    m = re.search(r"Building\s+([A-D])", building or "", re.IGNORECASE)
    return f"Bldg {m.group(1).upper()}" if m else (building or "?")


def _lookahead_deductions(activities):
    """Turn GC cross-check results into itemized health deductions (one per real gap)."""
    out = []
    for a in activities or []:
        status = a.get("status")
        if status not in _LOOKAHEAD_POINTS:
            continue  # on_track / complete cost nothing
        bldg = _short_building(a.get("building"))
        scope = _SCOPE_LABEL.get(a.get("scope"), a.get("scope") or "scope")
        need = a.get("gc_need")
        if status == "slip":
            days = a.get("slip_days") or 0
            pts = _LOOKAHEAD_SLIP_HIGH_POINTS if days > _LOOKAHEAD_SLIP_HIGH_DAYS else _LOOKAHEAD_POINTS["slip"]
            reason = f"{bldg} {scope} installs {a.get('our_date')} — {days}d after GC need {need}"
        elif status == "in_drafting":
            pts = _LOOKAHEAD_POINTS["in_drafting"]
            reason = f"{bldg} {scope} still in drafting — GC needs it {need}"
        else:  # no_record
            pts = _LOOKAHEAD_POINTS["no_record"]
            reason = f"{bldg} {scope} has no release — GC needs it {need}"
        out.append({"key": f"gc_{a.get('wbs_id')}", "count": 1, "points": pts, "reason": reason})
    return out


def _plural(n):
    return "" if n == 1 else "s"


def _deduction_reason(key, n):
    if key == "install_at_risk":
        their = "its" if n == 1 else "their"
        return f"{n} release{_plural(n)} past {their} install date, not yet complete"
    if key == "unsequenced_fab":
        return f"{n} release{_plural(n)} not sequenced into the shop queue (placeholder fab order)"
    if key == "overdue_submittal":
        return f"{n} submittal{_plural(n)} overdue"
    if key == "stale_drr":
        return f"{n} drafting release{_plural(n)} open with no dates set"
    return key


def _is_stale_drr(s):
    """A DRR still on the board (Open) with nothing scheduling it — no install or due date."""
    return (
        (s.type or "").strip().lower() == "drafting release review"
        and (s.status or "").strip().lower() == "open"
        and s.start_install is None
        and s.due_date is None
    )


def _project_state(releases):
    """Coarse lifecycle state that governs whether a numeric score is meaningful.

    A completed or fully-blocked project reads as neutral ("—"), not red — penalizing a
    paused or finished job would train the user to distrust the score.
    """
    if not releases:
        return "no_data"
    if all(r["pct"] >= 100 for r in releases):
        return "complete"
    non_complete = [r for r in releases if r["pct"] < 100]
    if non_complete and all(r["is_blocked"] for r in non_complete):
        return "on_hold"
    return "scored"


def _health_score(releases, submittal_models, submittals, lookahead=None):
    """Composite health as {score, band, state, deductions[]}. Computed, never stored.

    When `lookahead` (a crosscheck_for_job payload) is present, the GC-benchmark deductions
    fire and the generic internal `stale_drr` signal is suppressed — the lookahead's dated
    in_drafting/no_record deductions are the authoritative, non-duplicative version of it.
    """
    state = _project_state(releases)
    if state != "scored":
        return {"score": None, "band": "neutral", "state": state, "deductions": []}

    has_lookahead = bool(lookahead and lookahead.get("activities"))
    counts = {
        "install_at_risk": sum(1 for r in releases if r.get("at_risk")),
        "unsequenced_fab": sum(1 for r in releases if r.get("unsequenced")),
        "overdue_submittal": sum(1 for s in submittals if s.get("overdue")),
        # Superseded by the dated GC signal when a lookahead is present.
        "stale_drr": 0 if has_lookahead else sum(1 for s in submittal_models if _is_stale_drr(s)),
    }

    score = 100
    deductions = []
    for key, points, cap in SCORE_RUBRIC:
        n = counts.get(key, 0)
        if not n:
            continue
        pts = min(n * points, cap)
        score -= pts
        deductions.append(
            {"key": key, "count": n, "points": -pts, "reason": _deduction_reason(key, n)}
        )

    if has_lookahead:
        for d in _lookahead_deductions(lookahead["activities"]):
            score -= d["points"]
            deductions.append(
                {"key": d["key"], "count": d["count"], "points": -d["points"], "reason": d["reason"]}
            )

    score = max(0, score)
    band = "green" if score >= _GREEN_MIN else "amber" if score >= _AMBER_MIN else "red"
    deductions.sort(key=lambda d: d["points"])  # biggest hit first
    return {"score": score, "band": band, "state": "scored", "deductions": deductions}


def _upcoming_events(releases, within_days=21):
    """Non-complete install/ship dates within the window — the 'what's upcoming' feed."""
    today = date.today()
    horizon = today + timedelta(days=within_days)
    out = []
    for r in releases:
        if r["pct"] >= 100:
            continue
        for kind, iso in (("install", r.get("start_install")), ("ship", r.get("ship_date"))):
            if not iso:
                continue
            try:
                d = date.fromisoformat(iso)
            except (ValueError, TypeError):
                continue
            if today <= d <= horizon:
                out.append(
                    {
                        "kind": kind,
                        "date": iso,
                        "release": r["release"],
                        "description": r["description"],
                    }
                )
    out.sort(key=lambda e: e["date"])
    return out


def _project_rollup(release_models, submittal_models, lookahead=None):
    """Shared computed rollup for one project — used by both the index and the detail.

    `lookahead` (a crosscheck_for_job payload, or None) sharpens health_score with the
    GC-benchmark deductions when present.
    """
    releases = [_release_row(r) for r in release_models]
    submittals = [_submittal_row(s) for s in submittal_models]
    percent_complete = (
        round(sum(r["pct"] for r in releases) / len(releases)) if releases else 0
    )
    return {
        "releases": releases,
        "submittals": submittals,
        "percent_complete": percent_complete,
        "health": _health_tiles(releases, submittals),
        "health_score": _health_score(releases, submittal_models, submittals, lookahead),
        "upcoming": _upcoming_events(releases),
    }


# ---- public API -----------------------------------------------------------

def _job_number_as_int(job_number):
    try:
        return int(str(job_number).strip())
    except (TypeError, ValueError):
        return None


def _active_release_models(job_int):
    """Active Releases for a job number (int), ordered by release."""
    if job_int is None:
        return []
    return (
        Releases.query.filter(Releases.job == job_int)
        .filter(Releases.is_active.isnot(False))
        .order_by(Releases.release)
        .all()
    )


def _active_releases(project):
    """Value-joined Releases for a project (active only), ordered by release."""
    return _active_release_models(_job_number_as_int(project.job_number))


def _gc_and_name(job_name):
    """Split a job-log name like 'Wood Partners - Alta Metro Center' into (gc, project_name).

    The job log prefixes the GC; if there's no separator we treat the whole thing as the name.
    """
    if job_name and " - " in job_name:
        gc, _, rest = job_name.partition(" - ")
        return gc.strip(), rest.strip()
    return None, (job_name or "").strip()


def list_projects():
    """Index: every project + counts, PM, computed health_score band, and upcoming dates.

    The composite score and upcoming feed power the portfolio dashboard (health-band
    summary, cross-project "what's upcoming", at-risk callouts) on the overview page.
    """
    projects = Projects.query.order_by(Projects.job_number).all()
    out = []
    for p in projects:
        release_models = _active_releases(p)
        submittal_models = p.submittals.all()
        rollup = _project_rollup(release_models, submittal_models)
        out.append(
            {
                "id": p.id,
                "job_number": p.job_number,
                "name": p.name,
                "is_active": p.is_active,
                "address": p.address,
                "pm": p.pm.name if p.pm else None,
                "pm_color": p.pm.color if p.pm else None,
                "release_count": len(release_models),
                "submittal_count": len(submittal_models),
                "percent_complete": rollup["percent_complete"],
                "health_score": rollup["health_score"],
                "upcoming": rollup["upcoming"],
            }
        )
    return out


def get_project_live(job_number):
    """Full live payload for one project, assembled from the job log.

    Works two ways: if a `Projects` container row exists, identity comes from it; otherwise
    (e.g. job 560, which has releases/submittals but no geofence row) identity is derived
    from the job log itself, so any real job is viewable. Returns None only when the job
    number has no releases AND no submittals. `has_project_row` tells the UI which case it is.

    Populated from real sources: identity, releases, submittals, activity, health tiles, and
    the composite health_score. Financials/contract/customer have no source yet — the frontend
    supplies those from its demo scaffold (or marks them unavailable for a live-only job).
    """
    jn = str(job_number)
    job_int = _job_number_as_int(jn)
    project = Projects.query.filter(Projects.job_number == jn).first()

    if project is not None:
        release_models = _active_releases(project)
    else:
        release_models = _active_release_models(job_int)

    submittal_models = (
        Submittals.query.filter(Submittals.project_number == jn)
        .order_by(Submittals.order_number)
        .all()
    )

    # Truly not found: no container row, no releases, no submittals.
    if project is None and not release_models and not submittal_models:
        return None

    # Mock GC-lookahead cross-check (None unless this job is wired to a sample schedule).
    lookahead = lookahead_service.crosscheck_for_job(jn, release_models, submittal_models)
    rollup = _project_rollup(release_models, submittal_models, lookahead)
    activity = _activity_feed(job_int, [s.submittal_id for s in submittal_models])

    if project is not None:
        name = project.name
        gc = None
        is_active = project.is_active
        address = project.address
        pm = project.pm.name if project.pm else None
        pm_color = project.pm.color if project.pm else None
    else:
        job_name = release_models[0].job_name if release_models else jn
        gc, name = _gc_and_name(job_name)
        is_active = True
        address = None
        pm = pm_color = None

    return {
        "job_number": jn,
        "name": name,
        "gc": gc,
        "has_project_row": project is not None,
        "is_active": is_active,
        "address": address,
        "pm": pm,
        "pm_color": pm_color,
        "percent_complete": rollup["percent_complete"],
        "releases": rollup["releases"],
        "submittals": rollup["submittals"],
        "activity": activity,
        "health": rollup["health"],
        "health_score": rollup["health_score"],
        "upcoming": rollup["upcoming"],
        "lookahead": lookahead,
        # Sections with no backend source yet — flagged so the UI can mark them.
        "unavailable_sections": ["financials", "contract", "customer", "contacts", "documents"],
    }
