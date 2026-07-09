"""Assemble a holistic lifecycle bundle for a resolved anchor (release or submittal).

Deterministic, read-only: gathers the release(s) + the job's submittals + a merged,
chronological event timeline (ReleaseEvents + SubmittalEvents) + related to-dos, into one
JSON-serializable dict. The agent reasons over exactly this — it never queries the DB
itself, so it can't hallucinate a table or a number.

Event-payload shapes mirror app/history/__init__.py (releases: {'field','old_value',
'new_value'}; submittals: nested {field: {'old','new'}}).
"""
from app.logging_config import get_logger
from app.models import (
    ChecklistItem,
    Meeting,
    Releases,
    ReleaseEvents,
    Submittals,
    SubmittalEvents,
    User,
)

logger = get_logger(__name__)

_MAX_SUBMITTALS = 20
_MAX_TIMELINE = 80
_MAX_TODOS = 40
_TODO_STATUSES = ("proposed", "accepted", "done")  # exclude 'rejected'


def _d(value):
    """ISO-serialize a date/datetime, else pass through."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _release_view(r: Releases) -> dict:
    return {
        "job_release": f"{r.job}-{r.release}",
        "job": r.job,
        "release": r.release,
        "job_name": r.job_name,
        "description": r.description,
        "stage": r.stage,
        "stage_group": r.stage_group,
        "fab_order": r.fab_order,
        "pm": r.pm,
        "released": _d(r.released),
        "start_install": _d(r.start_install),
        "start_install_asap": r.start_install_asap,
        "comp_eta": _d(r.comp_eta),
        "num_guys": r.num_guys,
        "installer": r.installer,
        "job_comp": r.job_comp,       # 'X' or blank
        "invoiced": r.invoiced,       # 'X' or blank
        "fab_hrs": r.fab_hrs,
        "install_hrs": r.install_hrs,
        "notes": r.notes,
        "is_archived": r.is_archived,
    }


def _submittal_view(s: Submittals) -> dict:
    return {
        "submittal_id": s.submittal_id,
        "title": s.title,
        "type": s.type,
        "status": s.status,
        "ball_in_court": s.ball_in_court,
        "submittal_drafting_status": s.submittal_drafting_status,
        "due_date": _d(s.due_date),
        "gc_jobsite_schedule_date": _d(s.gc_jobsite_schedule_date),
        "rel": s.rel,
        "start_install": _d(s.start_install),
        "notes": s.notes,
    }


def _release_change(action: str, payload) -> str:
    if isinstance(payload, dict):
        if "field" in payload:
            return f"{payload['field']}: {payload.get('old_value')} → {payload.get('new_value')}"
        if "new_value" in payload:
            return str(payload["new_value"])
        if action == "list_move" and ("from_list" in payload or "to_list" in payload):
            return f"{payload.get('from_list')} → {payload.get('to_list')}"
    return action


def _submittal_change(action: str, payload) -> str:
    if isinstance(payload, dict):
        parts = []
        for k, v in payload.items():
            if isinstance(v, dict) and ("old" in v or "new" in v):
                parts.append(f"{k}: {v.get('old')} → {v.get('new')}")
        if parts:
            return "; ".join(parts)
        if "field" in payload:
            return f"{payload['field']}: {payload.get('old_value')} → {payload.get('new_value')}"
    return action


def _timeline(release_keys, submittal_ids) -> tuple:
    """Merged chronological event timeline for the given releases + submittals."""
    entries = []

    if release_keys:
        rev_q = ReleaseEvents.query.filter(ReleaseEvents.is_system_echo.is_(False))
        # release_keys is a list of (job, release) pairs.
        jobs = {j for j, _ in release_keys}
        rels = {r for _, r in release_keys}
        rev = rev_q.filter(ReleaseEvents.job.in_(jobs), ReleaseEvents.release.in_(rels)).all()
        wanted = set(release_keys)
        for e in rev:
            if (e.job, e.release) not in wanted:
                continue
            entries.append({
                "when": _d(e.created_at),
                "kind": "release",
                "ref": f"{e.job}-{e.release}",
                "action": e.action,
                "source": e.source,
                "change": _release_change(e.action, e.payload),
            })

    if submittal_ids:
        sev = SubmittalEvents.query.filter(
            SubmittalEvents.is_system_echo.is_(False),
            SubmittalEvents.submittal_id.in_(submittal_ids),
        ).all()
        for e in sev:
            entries.append({
                "when": _d(e.created_at),
                "kind": "submittal",
                "ref": e.submittal_id,
                "action": e.action,
                "source": e.source,
                "change": _submittal_change(e.action, e.payload),
            })

    entries.sort(key=lambda x: (x["when"] or ""))
    omitted = 0
    if len(entries) > _MAX_TIMELINE:
        omitted = len(entries) - _MAX_TIMELINE
        entries = entries[-_MAX_TIMELINE:]  # keep the most recent, still chronological
    return entries, omitted


def _todos(release_ids, submittal_ids, job) -> list:
    conds = []
    if release_ids:
        conds.append(ChecklistItem.release_id.in_(release_ids))
    if submittal_ids:
        conds.append(ChecklistItem.submittal_id.in_(submittal_ids))
    if job is not None:
        conds.append(ChecklistItem.matched_job_number == str(job))
    if not conds:
        return []
    from app.models import db
    items = (
        ChecklistItem.query
        .filter(db.or_(*conds), ChecklistItem.status.in_(_TODO_STATUSES))
        .order_by(ChecklistItem.due_date.is_(None), ChecklistItem.due_date)
        .limit(_MAX_TODOS)
        .all()
    )
    # Resolve owner + source meeting names in bulk.
    owner_ids = {i.owner_user_id for i in items if i.owner_user_id}
    owners = {u.id: (u.first_name or u.username) for u in
              User.query.filter(User.id.in_(owner_ids)).all()} if owner_ids else {}
    meeting_ids = {i.meeting_id for i in items if i.meeting_id}
    meetings = {m.id: m.title for m in
                Meeting.query.filter(Meeting.id.in_(meeting_ids)).all()} if meeting_ids else {}
    out = []
    for i in items:
        out.append({
            "title": i.title,
            "detail": i.detail,
            "status": i.status,
            "item_type": i.item_type,
            "gc_facing": i.gc_facing,
            "due_date": _d(i.due_date),
            "owner": owners.get(i.owner_user_id),
            "from_meeting": meetings.get(i.meeting_id),
        })
    return out


def assemble(anchor: dict) -> dict:
    """Build the lifecycle bundle for a resolved anchor. Returns a JSON-serializable dict."""
    job = anchor.get("job")
    releases = []
    submittals = []

    if anchor["kind"] == "submittal":
        # Anchor is one named submittal; pull its job's releases for context.
        s = Submittals.query.filter_by(submittal_id=anchor["submittal_id"]).first()
        submittals = [s] if s else []
        if s and (s.project_number or "").isdigit():
            job = int(s.project_number)
        if job is not None:
            releases = (Releases.query.filter(Releases.job == job, Releases.is_archived.is_(False))
                        .order_by(Releases.release).all())
    else:
        # Anchor is a release (exact) or a whole job (release=None).
        if anchor.get("release"):
            releases = Releases.query.filter_by(job=job, release=anchor["release"]).all()
        elif job is not None:
            releases = (Releases.query.filter(Releases.job == job, Releases.is_archived.is_(False))
                        .order_by(Releases.release).all())
        if job is not None:
            submittals = (Submittals.query.filter_by(project_number=str(job))
                          .order_by(Submittals.order_number).limit(_MAX_SUBMITTALS).all())

    release_keys = [(r.job, r.release) for r in releases]
    release_ids = [r.id for r in releases]
    submittal_ids = [s.submittal_id for s in submittals]

    timeline, omitted = _timeline(release_keys, submittal_ids)
    todos = _todos(release_ids, submittal_ids, job)

    return {
        "anchor": {"kind": anchor["kind"], "label": anchor.get("label"),
                   "job": job, "release": anchor.get("release"),
                   "submittal_id": anchor.get("submittal_id")},
        "releases": [_release_view(r) for r in releases],
        "submittals": [_submittal_view(s) for s in submittals],
        "timeline": timeline,
        "timeline_omitted_older": omitted,
        "todos": todos,
        "counts": {
            "releases": len(releases),
            "submittals": len(submittals),
            "events": len(timeline) + omitted,
            "todos": len(todos),
        },
        "found": bool(releases or submittals),
    }
