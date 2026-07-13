"""Read-only tools BB can invoke via Anthropic tool-use.

Ported from the original app/banana_boy/tools.py (feature/banana-boy-v2), trimmed to the
READ-ONLY suite (the Gmail draft/send write tools are intentionally excluded — V1 is
read-only), plus two additions for this branch:
  - get_release_lifecycle  → the deterministic lifecycle bundle (app/brain/bb_chat/assembler)
  - search_todos           → meeting-derived to-dos (ChecklistItem) by owner/job

Each tool has a JSON-Schema definition in `TOOL_DEFINITIONS` and an executor in
`TOOL_EXECUTORS`. User-scoped tools read `context["user_id"]` — never a model-supplied id.
"""
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import joinedload

from app.history import _extract_new_value_from_payload
from app.logging_config import get_logger
from app.models import (
    ChecklistItem,
    Meeting,
    Notification,
    Releases,
    ReleaseEvents,
    Submittals,
    User,
    db,
)

from .assembler import assemble

logger = get_logger(__name__)

TOOL_SEARCH_BY_ID = "search_jobs_by_identifier"
TOOL_SEARCH_BY_NAME = "search_jobs_by_project_name"
TOOL_RELEASE_HISTORY = "get_release_history"
TOOL_RELEASE_LIFECYCLE = "get_release_lifecycle"
TOOL_SEARCH_SUBMITTALS = "search_submittals"
TOOL_SEARCH_TODOS = "search_todos"
TOOL_NOTIFICATIONS = "get_my_notifications"

MAX_RESULTS = 25

TOOL_DEFINITIONS = [
    {
        "name": TOOL_SEARCH_BY_ID,
        "description": (
            "Look up a release by its job/release identifier. Accepts '410-271', "
            "'410 271', '410271', or just '410' (all releases for that job). Use when "
            "the user mentions a specific job or release number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "Job or job-release, e.g. '410-271' or '410'."},
            },
            "required": ["identifier"],
        },
    },
    {
        "name": TOOL_SEARCH_BY_NAME,
        "description": (
            "Search releases by project name (substring, case-insensitive). Use when the "
            "user names a project (e.g. 'Lennar Columbine')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Project name fragment."},
                "limit": {"type": "integer", "description": "Max results (default 20).", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": TOOL_RELEASE_HISTORY,
        "description": (
            "Fetch the change history (audit trail) for one release, newest-first. Use for "
            "'what happened to', 'when did X change', 'who released it', 'show the changelog'. "
            "For a full summary of a release, prefer get_release_lifecycle instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {"type": "integer", "description": "Job number, e.g. 370."},
                "release": {"type": "string", "description": "Release number, e.g. '406'."},
                "max_events": {"type": "integer", "description": "Max events (default 50, cap 100).", "default": 50},
            },
            "required": ["job", "release"],
        },
    },
    {
        "name": TOOL_RELEASE_LIFECYCLE,
        "description": (
            "Assemble the WHOLE lifecycle of a release in one call: its current state, the "
            "job's submittals, a merged chronological event timeline (releases + submittals), "
            "and related to-dos. Use this when the user asks to 'summarize' a release or job, "
            "or wants the full picture / where it stands / its lifecycle. Prefer this over "
            "calling search + history separately for a summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {"type": "integer", "description": "Job number, e.g. 290."},
                "release": {"type": "string", "description": "Release number, e.g. '153'. Omit to cover the whole job (all its releases)."},
            },
            "required": ["job"],
        },
    },
    {
        "name": TOOL_SEARCH_SUBMITTALS,
        "description": (
            "Search Procore submittals. Call when the user mentions 'submittals' or asks about "
            "ball-in-court ownership ('what's on Colton's plate', 'submittals in Daniel's court'). "
            "Do NOT call for bare project/identifier queries — those are release-only. Pass at "
            "least one filter. Each result includes days_since_bic_update (aging), days_until_due "
            "(negative ⇒ overdue), and order_number (lower = more urgent)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Project name fragment (substring)."},
                "project_number": {"type": "string", "description": "Exact project/job number (string)."},
                "ball_in_court": {"type": "string", "description": "Person currently owning the submittal — substring match against the comma-separated assignee field, e.g. 'Colton'."},
                "submittal_manager": {"type": "string", "description": "Submittal manager name fragment."},
                "urgent_only": {"type": "boolean", "description": "Restrict to urgent submittals (order_number < 1), most urgent first.", "default": False},
                "limit": {"type": "integer", "description": "Max rows (default 20, cap 100).", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": TOOL_SEARCH_TODOS,
        "description": (
            "Find to-dos (meeting-derived action items). Use for 'what's on Colton's to-do list', "
            "'to-dos for X', or to-dos tied to a job/release. Filter by owner (person's first name) "
            "and/or job. Returns open action items with owner, due date, and source meeting. Note: "
            "ball-in-court SUBMITTAL ownership is a different thing — use search_submittals for that."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Person the to-do is assigned to (first name, substring), e.g. 'Colton'."},
                "job": {"type": "integer", "description": "Job number to scope to."},
                "release": {"type": "string", "description": "Release number (use with job)."},
                "status": {"type": "string", "description": "One of: proposed | accepted | done. Default: open (accepted + proposed + done)."},
                "limit": {"type": "integer", "description": "Max rows (default 20, cap 50).", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": TOOL_NOTIFICATIONS,
        "description": (
            "Fetch the CURRENT signed-in user's notifications (mentions/alerts). Use for 'do I "
            "have any mentions', 'what's new for me'. Always the session user — never a supplied id. "
            "For ball-in-court / on-my-plate questions use search_submittals; for to-dos use search_todos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "unread_only": {"type": "boolean", "description": "Only unread (default true).", "default": True},
                "limit": {"type": "integer", "description": "Max results (default 20, cap 50).", "default": 20},
            },
            "required": [],
        },
    },
]


def _clamp_limit(value, default: int, ceiling: int = MAX_RESULTS) -> int:
    try:
        n = int(value) if value is not None else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, ceiling))


def _release_to_compact(r: Releases) -> dict:
    return {
        "job": r.job,
        "release": r.release,
        "identifier": f"{r.job}-{r.release}",
        "project_name": r.job_name,
        "description": r.description,
        "fab_hrs": r.fab_hrs,
        "install_hrs": r.install_hrs,
        "pm": r.pm,
        "drafter": r.by,
        "stage": r.stage,
        "stage_group": r.stage_group,
        "released_on": r.released.isoformat() if r.released else None,
        "start_install": r.start_install.isoformat() if r.start_install else None,
        "comp_eta": r.comp_eta.isoformat() if r.comp_eta else None,
        "job_comp": r.job_comp,   # 'X' = complete
        "invoiced": r.invoiced,   # 'X' = complete
        "fab_order": r.fab_order,
        "is_archived": r.is_archived,
        "notes": r.notes,
    }


def _parse_identifier(identifier: str):
    """Return (job:int, release:str|None) or (None, None). Accepts '410-271','410 271','410271','410'."""
    if not identifier:
        return None, None
    s = str(identifier).strip()
    if not s:
        return None, None
    parts = re.split(r"[\s\-/]+", s)
    if len(parts) >= 2 and parts[0].isdigit() and parts[1]:
        try:
            return int(parts[0]), parts[1]
        except ValueError:
            pass
    if s.isdigit():
        if len(s) >= 5:
            return int(s[:3]), s[3:]
        return int(s), None
    return None, None


def search_jobs_by_identifier(identifier: str) -> dict[str, Any]:
    job, release = _parse_identifier(identifier)
    if job is None:
        return {"error": f"Could not parse '{identifier}'. Try '410-271' or just '410'.", "results": []}
    q = Releases.query.filter(Releases.job == job)
    if release:
        q = q.filter(Releases.release == release)
    rows = q.order_by(Releases.release.asc()).limit(MAX_RESULTS).all()
    return {"query": {"job": job, "release": release}, "result_count": len(rows),
            "results": [_release_to_compact(r) for r in rows]}


def search_jobs_by_project_name(query: str, limit: int = 20) -> dict[str, Any]:
    if not query or not query.strip():
        return {"error": "query is required", "results": []}
    limit = _clamp_limit(limit, default=20)
    rows = (Releases.query.filter(Releases.job_name.ilike(f"%{query.strip()}%"))
            .order_by(Releases.job.asc(), Releases.release.asc()).limit(limit).all())
    return {"query": {"project_name_contains": query, "limit": limit},
            "result_count": len(rows), "results": [_release_to_compact(r) for r in rows]}


def get_release_history(job: int, release: str, max_events: int = 50,
                        include_system_echoes: bool = False) -> dict[str, Any]:
    if job is None or release is None or str(release).strip() == "":
        return {"error": "both job and release are required", "events": []}
    try:
        job_int = int(job)
    except (TypeError, ValueError):
        return {"error": f"invalid job number: {job!r}", "events": []}
    release_str = str(release)
    max_events = _clamp_limit(max_events, default=50, ceiling=100)

    q = (ReleaseEvents.query.options(joinedload(ReleaseEvents.user))
         .filter(ReleaseEvents.job == job_int, ReleaseEvents.release == release_str))
    if not include_system_echoes:
        q = q.filter(ReleaseEvents.is_system_echo == False)  # noqa: E712
    total = q.count()
    rows = q.order_by(ReleaseEvents.created_at.desc()).limit(max_events).all()

    events = []
    for ev in rows:
        actor = (ev.user.first_name or ev.user.username) if ev.user is not None else None
        payload = ev.payload or {}
        events.append({
            "id": ev.id,
            "when": ev.created_at.isoformat() if ev.created_at else None,
            "action": ev.action,
            "summary": _extract_new_value_from_payload(ev.action, payload),
            "source": ev.source,
            "actor_name": actor,
        })
    return {"query": {"job": job_int, "release": release_str}, "total_event_count": total,
            "returned_event_count": len(events), "events": events}


def get_release_lifecycle(job: int, release: str | None = None) -> dict[str, Any]:
    """The full assembled lifecycle bundle (release + submittals + timeline + to-dos)."""
    try:
        job_int = int(job)
    except (TypeError, ValueError):
        return {"error": f"invalid job number: {job!r}", "found": False}
    label = f"release {job_int}-{release}" if release else f"job {job_int}"
    return assemble({"kind": "release", "job": job_int,
                     "release": str(release) if release else None,
                     "submittal_id": None, "label": label})


def _submittal_to_compact(s: Submittals) -> dict:
    today = date.today()
    days_since_bic = (datetime.utcnow() - s.last_bic_update).days if s.last_bic_update else None
    lifespan = None
    if s.created_at:
        created_d = s.created_at.date() if hasattr(s.created_at, "date") else s.created_at
        lifespan = (today - created_d).days
    days_until_due = (s.due_date - today).days if s.due_date else None
    notes = s.notes
    if notes and len(notes) > 400:
        notes = notes[:400] + "…"
    return {
        "submittal_id": s.submittal_id,
        "title": s.title,
        "status": s.status,
        "type": s.type,
        "ball_in_court": s.ball_in_court,
        "submittal_manager": s.submittal_manager,
        "order_number": s.order_number,
        "drafting_status": s.submittal_drafting_status,
        "due_date": s.due_date.isoformat() if s.due_date else None,
        "days_until_due": days_until_due,
        "project_number": s.project_number,
        "project_name": s.project_name,
        "notes": notes,
        "days_since_bic_update": days_since_bic,
        "lifespan_days": lifespan,
    }


def search_submittals(project_name: str | None = None, project_number: str | None = None,
                      ball_in_court: str | None = None, submittal_manager: str | None = None,
                      urgent_only: bool = False, limit: int = 20) -> dict[str, Any]:
    if not (project_name or project_number or ball_in_court or submittal_manager or urgent_only):
        return {"error": "pass at least one filter (project_name, project_number, ball_in_court, submittal_manager, or urgent_only)", "results": []}
    limit = _clamp_limit(limit, default=20, ceiling=100)

    q = Submittals.query
    if project_number:
        q = q.filter(Submittals.project_number == str(project_number))
    if project_name:
        q = q.filter(Submittals.project_name.ilike(f"%{project_name.strip()}%"))
    if ball_in_court:
        # ball_in_court is a comma-separated multi-assignee string; substring handles partials.
        q = q.filter(Submittals.ball_in_court.ilike(f"%{ball_in_court.strip()}%"))
    if submittal_manager:
        q = q.filter(Submittals.submittal_manager.ilike(f"%{submittal_manager.strip()}%"))
    if urgent_only:
        q = q.filter(Submittals.order_number < 1)

    if urgent_only:
        q = q.order_by(Submittals.order_number.asc().nullslast(), Submittals.last_updated.desc())
    else:
        q = q.order_by(Submittals.last_updated.desc().nullslast(), Submittals.created_at.desc())
    rows = q.limit(limit).all()
    return {
        "query": {"project_name": project_name, "project_number": project_number,
                  "ball_in_court": ball_in_court, "submittal_manager": submittal_manager,
                  "urgent_only": urgent_only, "limit": limit},
        "result_count": len(rows),
        "results": [_submittal_to_compact(s) for s in rows],
    }


_TODO_OPEN_STATUSES = ("accepted", "proposed", "done")


def search_todos(owner: str | None = None, job: int | None = None, release: str | None = None,
                 status: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Meeting-derived to-dos (ChecklistItem), filtered by owner (person) and/or job/release."""
    limit = _clamp_limit(limit, default=20, ceiling=50)
    q = ChecklistItem.query
    applied = False

    if owner:
        like = f"%{owner.strip()}%"
        uids = [u.id for u in User.query.filter(
            db.or_(User.first_name.ilike(like), User.last_name.ilike(like), User.username.ilike(like))
        ).all()]
        if not uids:
            return {"query": {"owner": owner}, "result_count": 0, "results": [],
                    "note": f"no user matching '{owner}'"}
        q = q.filter(ChecklistItem.owner_user_id.in_(uids))
        applied = True

    if job is not None:
        try:
            job_int = int(job)
        except (TypeError, ValueError):
            return {"error": f"invalid job number: {job!r}", "results": []}
        rel_q = Releases.query.filter(Releases.job == job_int)
        if release:
            rel_q = rel_q.filter(Releases.release == str(release))
        rel_ids = [r.id for r in rel_q.all()]
        job_conds = [ChecklistItem.matched_job_number == str(job_int)]
        if rel_ids:
            job_conds.append(ChecklistItem.release_id.in_(rel_ids))
        q = q.filter(db.or_(*job_conds))
        applied = True

    if not applied:
        return {"error": "pass at least one filter (owner, or job)", "results": []}

    statuses = [status] if status else list(_TODO_OPEN_STATUSES)
    q = q.filter(ChecklistItem.status.in_(statuses))
    rows = q.order_by(ChecklistItem.due_date.is_(None), ChecklistItem.due_date).limit(limit).all()

    owner_ids = {i.owner_user_id for i in rows if i.owner_user_id}
    owners = {u.id: (u.first_name or u.username) for u in
              User.query.filter(User.id.in_(owner_ids)).all()} if owner_ids else {}
    mtg_ids = {i.meeting_id for i in rows if i.meeting_id}
    mtgs = {m.id: m.title for m in Meeting.query.filter(Meeting.id.in_(mtg_ids)).all()} if mtg_ids else {}
    rel_ids = {i.release_id for i in rows if i.release_id}
    rels = {r.id: f"{r.job}-{r.release}" for r in Releases.query.filter(Releases.id.in_(rel_ids)).all()} if rel_ids else {}

    results = []
    for i in rows:
        detail = i.detail
        if detail and len(detail) > 300:
            detail = detail[:300] + "…"
        results.append({
            "title": i.title,
            "detail": detail,
            "status": i.status,
            "item_type": i.item_type,
            "gc_facing": i.gc_facing,
            "due_date": i.due_date.isoformat() if i.due_date else None,
            "owner": owners.get(i.owner_user_id),
            "job_release": rels.get(i.release_id) or i.matched_job_number,
            "from_meeting": mtgs.get(i.meeting_id),
        })
    return {"query": {"owner": owner, "job": job, "release": release, "status": status, "limit": limit},
            "result_count": len(results), "results": results}


def get_my_notifications(context: dict, unread_only: bool = True, limit: int = 20) -> dict[str, Any]:
    user_id = context.get("user_id")
    if not user_id:
        return {"error": "no signed-in user", "results": []}
    limit = _clamp_limit(limit, default=20, ceiling=50)
    q = Notification.query.filter_by(user_id=user_id)
    if unread_only:
        q = q.filter_by(is_read=False)
    rows = q.order_by(Notification.created_at.desc()).limit(limit).all()
    results = []
    for n in rows:
        item = {"id": n.id, "type": n.type, "message": n.message, "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None}
        if n.submittal is not None:
            item["submittal"] = {"submittal_id": n.submittal.submittal_id, "title": n.submittal.title,
                                 "project_number": n.submittal.project_number, "status": n.submittal.status,
                                 "ball_in_court": n.submittal.ball_in_court}
        results.append(item)
    return {"query": {"unread_only": unread_only, "limit": limit},
            "result_count": len(results), "results": results}


USER_SCOPED_TOOLS = {TOOL_NOTIFICATIONS}

TOOL_EXECUTORS = {
    TOOL_SEARCH_BY_ID: search_jobs_by_identifier,
    TOOL_SEARCH_BY_NAME: search_jobs_by_project_name,
    TOOL_RELEASE_HISTORY: get_release_history,
    TOOL_RELEASE_LIFECYCLE: get_release_lifecycle,
    TOOL_SEARCH_SUBMITTALS: search_submittals,
    TOOL_SEARCH_TODOS: search_todos,
    TOOL_NOTIFICATIONS: get_my_notifications,
}


def execute_tool(name: str, arguments: dict, context: dict | None = None) -> dict[str, Any]:
    """Dispatch a tool call by name. Returns a JSON-serializable dict."""
    fn = TOOL_EXECUTORS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        if name in USER_SCOPED_TOOLS:
            return fn(context or {}, **(arguments or {}))
        return fn(**(arguments or {}))
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        logger.error("bb_chat_tool_failed", tool=name, error=str(exc), exc_info=True)
        db.session.rollback()  # reset a possibly-aborted transaction
        return {"error": f"tool {name} failed: {exc}"}
