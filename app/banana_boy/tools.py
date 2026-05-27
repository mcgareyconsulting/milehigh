"""Tool implementations Banana Boy can invoke via Anthropic tool-use.

Each tool has:
  - a JSON-Schema definition exposed to Claude (`TOOL_DEFINITIONS`)
  - a Python executor mapped by name in `TOOL_EXECUTORS`

User-scoped tools read `context["user_id"]` rather than trusting any
user-supplied identifier — never let the LLM pretend to be a different user.
"""
import re
from datetime import date, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy.orm import joinedload

from app.auth.google_tokens import GoogleAuthError
from app.banana_boy.compliance import scan_pdf
from app.banana_boy.gmail_client import GmailScopeError, create_draft, send_draft
from app.banana_boy.markup_diff import scan_markup_diff_pdfs
from app.brain.job_log.scheduling.installer_availability import (
    default_window_days,
    find_conflicts,
    release_window,
    team_availability,
)
from app.config import Config
from app.history import _extract_new_value_from_payload
from app.logging_config import get_logger
from app.models import (
    Notification,
    PickupOrder,
    ReleaseDrawingVersion,
    ReleaseEvents,
    Releases,
    Submittals,
    db,
)

logger = get_logger(__name__)

TOOL_SEARCH_BY_ID = "search_jobs_by_identifier"
TOOL_SEARCH_BY_NAME = "search_jobs_by_project_name"
TOOL_RELEASE_HISTORY = "get_release_history"
TOOL_SEARCH_SUBMITTALS = "search_submittals"
TOOL_CREATE_DRAFT = "create_email_draft"
TOOL_SEND_DRAFT = "send_email_draft"
TOOL_NOTIFICATIONS = "get_my_notifications"
TOOL_SCAN_COMPLIANCE = "scan_drawing_compliance"
TOOL_LIST_DRAWING_VERSIONS = "list_drawing_versions"
TOOL_SCAN_MARKUP_DIFF = "scan_markup_diff"
TOOL_GET_PICKUP = "get_release_pickup"
TOOL_PROPOSE_RESCHEDULE = "propose_reschedule_install"

# Tools whose structured result is surfaced to the frontend (e.g. for a
# confirmation card) in addition to the model's text reply. See client.py.
SURFACEABLE_ACTION_TOOLS = {TOOL_PROPOSE_RESCHEDULE}

# Max characters of pickup email body to feed the model (keeps token use sane).
PICKUP_BODY_MAX_CHARS = 4000

DRAWING_LOADER_KEY = "banana_boy_drawings"

TOOL_DEFINITIONS = [
    {
        "name": TOOL_SEARCH_BY_ID,
        "description": (
            "Look up a release by its 6-digit job/release identifier. "
            "Accepts forms like '410-271', '410 271', '410271', or just '410' "
            "(returns all releases for that job). Use this when the user "
            "mentions a specific job or release number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": (
                        "Job or job-release identifier. Examples: '410-271', "
                        "'410 271', '410271', '410'."
                    ),
                },
            },
            "required": ["identifier"],
        },
    },
    {
        "name": TOOL_SEARCH_BY_NAME,
        "description": (
            "Search releases by project name (job_name). Substring, "
            "case-insensitive. Use when the user mentions a project by name "
            "(e.g., 'Lennar Columbine', 'Brinkman Marshall')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Project name fragment to search for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 20).",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": TOOL_RELEASE_HISTORY,
        "description": (
            "Fetch the full change history (audit trail) for a release. Use "
            "this when the user asks 'what happened to', 'when did X change', "
            "'who released it', 'show me the changelog', or after looking up "
            "a release with search_jobs_by_identifier and the user wants more "
            "than the current snapshot. Returns events newest-first. Filters "
            "out system echoes by default."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {
                    "type": "integer",
                    "description": "Job number, e.g. 370.",
                },
                "release": {
                    "type": "string",
                    "description": "Release number, e.g. '406'.",
                },
                "max_events": {
                    "type": "integer",
                    "description": "Max events to return (default 50, hard cap 100).",
                    "default": 50,
                },
                "include_system_echoes": {
                    "type": "boolean",
                    "description": "Include is_system_echo=True rows. Default false.",
                    "default": False,
                },
            },
            "required": ["job", "release"],
        },
    },
    {
        "name": TOOL_GET_PICKUP,
        "description": (
            "Fetch the vendor part pick-up order(s) for a release — the "
            "forwarded Dencol 'PU' / parts-pickup email. Call this when the "
            "user asks about a pickup, a Dencol order, a 'PU' email, or 'what "
            "parts are we picking up' for a release. When the user wants the "
            "full rundown on a release, call search_jobs_by_identifier, "
            "get_release_history, AND get_release_pickup together. Returns the "
            "email subject/sender/received date and body, newest pickup first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {"type": "integer", "description": "Job number, e.g. 380."},
                "release": {"type": "string", "description": "Release number, e.g. '456'."},
            },
            "required": ["job", "release"],
        },
    },
    {
        "name": TOOL_PROPOSE_RESCHEDULE,
        "description": (
            "Propose moving a release's install — a new start_install date "
            "and/or a different installer team — and CHECK FOR CONFLICTS. This "
            "tool is READ-ONLY: it never changes anything. It returns whether "
            "the requested installer team is free in the new window, which "
            "teams ARE free, and any conflicting releases. The app shows the "
            "user a confirmation card to actually commit the change. "
            "Call this when the user wants to move/push/reschedule a start "
            "install date ('move start install to next week', 'push 380-456 "
            "to June 9') or reassign the installer ('put it on Saul 2'). "
            "Resolve relative dates ('next week', 'tomorrow') to a concrete "
            "YYYY-MM-DD using 'today' from the Current user block. After "
            "calling, tell the user whether the team is free or conflicts, and "
            "list the open teams — but NEVER say the change is done; the user "
            "confirms it in the card."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {"type": "integer", "description": "Job number, e.g. 380."},
                "release": {"type": "string", "description": "Release number, e.g. '456'."},
                "new_start_install": {
                    "type": "string",
                    "description": (
                        "New install start date as YYYY-MM-DD. Resolve relative "
                        "phrases to a concrete date using today's date."
                    ),
                },
                "requested_installer": {
                    "type": "string",
                    "description": (
                        "Installer team the user asked for (e.g. 'Saul 2'). "
                        "Omit to keep the current team."
                    ),
                },
                "new_comp_eta": {
                    "type": "string",
                    "description": (
                        "Optional explicit completion date YYYY-MM-DD. If "
                        "omitted, the install duration is preserved (or derived "
                        "from install hours)."
                    ),
                },
            },
            "required": ["job", "release", "new_start_install"],
        },
    },
    {
        "name": TOOL_SEARCH_SUBMITTALS,
        "description": (
            "Search Procore submittals. ONLY call when the user explicitly "
            "mentions 'submittals' or asks about ball-in-court ownership "
            "(e.g. 'what's on Daniel's plate'). Do NOT call for bare project "
            "queries ('tell me about Lennar Columbine', 'project 350') or "
            "for job-release identifiers ('440-271') — those are release-only. "
            "If the user says 'pull submittals AND releases for 350', call "
            "both this tool and search_jobs_by_identifier in the same turn. "
            "Pass at least one filter. "
            "For DWL / urgency analysis: combine urgent_only=True with a "
            "high limit (e.g. 100) to pull the full urgency ladder, then "
            "group results by submittal_manager when the user asks for a "
            "'by submittal manager' or 'per submittal manager' summary. "
            "Each result includes days_since_bic_update (aging signal), "
            "days_until_due (negative ⇒ overdue), lifespan_days, and notes — "
            "use these to surface delayed projects vs. healthy ones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Project name fragment (substring, case-insensitive). Example: 'Lennar Columbine'.",
                },
                "project_number": {
                    "type": "string",
                    "description": "Exact project number (string in DB). Use after release lookup gives you a job number.",
                },
                "ball_in_court": {
                    "type": "string",
                    "description": "Person currently owning the submittal. Substring match against the comma-separated assignee field. Example: 'Daniel'.",
                },
                "submittal_manager": {
                    "type": "string",
                    "description": "Submittal manager name fragment (substring, case-insensitive). Use to filter or drill into a single submittal manager's submittals when the user asks 'urgent submittals for submittal manager X' or wants to focus on one manager.",
                },
                "urgent_only": {
                    "type": "boolean",
                    "description": "If true, restrict to urgent submittals — defined as order_number < 1. Sorted by order_number ascending (most urgent first). Use when the user asks 'what's urgent', 'urgent submittals', 'priority submittals', or combines urgency with another filter (e.g. 'urgent ones in my court').",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows (default 20, hard cap 100). Use 100 for full DWL/urgency-by-PM summaries.",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": TOOL_CREATE_DRAFT,
        "description": (
            "Create a Gmail draft on the signed-in user's behalf. ALWAYS use "
            "this when the user asks to email someone — never claim to have "
            "sent an email without first creating a draft and getting "
            "explicit user confirmation. Returns a draft_id you can later "
            "pass to send_email_draft. Always summarize the draft (to, "
            "subject, body) and ask the user to confirm before sending."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Plain-text email body."},
                "cc": {"type": "string", "description": "Optional CC recipient(s), comma-separated."},
                "bcc": {"type": "string", "description": "Optional BCC recipient(s), comma-separated."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": TOOL_SEND_DRAFT,
        "description": (
            "Send a previously-created Gmail draft. Only call this AFTER the "
            "user has explicitly confirmed (e.g. 'yes send it', 'go ahead'). "
            "Never call without an explicit user confirmation in the most "
            "recent message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "The draft_id returned by create_email_draft.",
                },
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": TOOL_NOTIFICATIONS,
        "description": (
            "Fetch the current signed-in user's notifications. Use this when "
            "the user asks 'what's on my to-do', 'what do I have to do', "
            "'do I have any mentions', or 'what's new for me'. Always uses "
            "the current session user — never accepts a user id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "unread_only": {
                    "type": "boolean",
                    "description": "If true (default), only return unread notifications.",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 20, max 50).",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": TOOL_SCAN_COMPLIANCE,
        "description": (
            "Scan a job-release fab-drawing PDF for code compliance issues "
            "(IBC, ADA, AISC, AWS, OSHA per the Division 05 KB). Hands the "
            "drawing to a vision-capable sub-agent that returns PASSING / "
            "FLAGGED / NOT_DETERMINABLE findings with verbatim page citations. "
            "When the release has marked-up drawing versions on file, this "
            "automatically scans the latest marked-up version (so drafter "
            "redlines and text annotations are picked up); otherwise it falls "
            "back to the on-disk fab PDF. ALWAYS call this for specific-job "
            "compliance questions ('is 480-299 compliant?', 'check 410-271 "
            "for code issues', 'any compliance issues on the Alta Flatirons "
            "fab package?'). Do NOT answer compliance questions about a "
            "specific job from the KB alone. Returns {error} when no fab PDF "
            "is on file for that release — relay that fact to the user "
            "verbatim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {
                    "type": "integer",
                    "description": "Job number, e.g. 480.",
                },
                "release": {
                    "type": "string",
                    "description": "Release number, e.g. '299'.",
                },
            },
            "required": ["job", "release"],
        },
    },
    {
        "name": TOOL_LIST_DRAWING_VERSIONS,
        "description": (
            "List the marked-up drawing versions on file for a job-release. "
            "Returns version_number (1 = original upload), uploaded_by, "
            "uploaded_at, note, and source_version_id (which prior version "
            "this one was derived from). Use this when the user asks about "
            "drawing history ('what versions of the drawing for 480-299 do "
            "we have?', 'who marked up the latest 410-271 drawing?', 'list "
            "drawing versions for ...'). Returns an empty list when no "
            "versions exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {
                    "type": "integer",
                    "description": "Job number, e.g. 480.",
                },
                "release": {
                    "type": "string",
                    "description": "Release number, e.g. '299'.",
                },
            },
            "required": ["job", "release"],
        },
    },
    {
        "name": TOOL_SCAN_MARKUP_DIFF,
        "description": (
            "Compare two marked-up drawing versions for a release and report "
            "what changed between them. Hands BOTH PDFs to a vision-capable "
            "sub-agent which returns the markups added between the 'from' "
            "and 'to' versions — text annotations quoted verbatim, ink and "
            "stamp annotations described spatially, by page. Defaults: 'to' "
            "= latest version, 'from' = the version it was derived from "
            "(source_version_id) or the immediately previous version_number "
            "if the lineage link is missing. Use when the user asks 'what "
            "changed in the latest markup', 'what did <person> add to the "
            "drawing', 'show me the redlines on 480-299'. Returns {error} "
            "when the release does not have at least two versions on file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job": {
                    "type": "integer",
                    "description": "Job number, e.g. 480.",
                },
                "release": {
                    "type": "string",
                    "description": "Release number, e.g. '299'.",
                },
                "from_version": {
                    "type": "integer",
                    "description": (
                        "Optional version_number to diff from (the earlier "
                        "version). Defaults to the predecessor of `to_version`."
                    ),
                },
                "to_version": {
                    "type": "integer",
                    "description": (
                        "Optional version_number to diff to (the later "
                        "version). Defaults to the latest non-deleted version."
                    ),
                },
            },
            "required": ["job", "release"],
        },
    },
]

MAX_RESULTS = 25


def _clamp_limit(value, default: int, ceiling: int = MAX_RESULTS) -> int:
    try:
        n = int(value) if value is not None else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, ceiling))


def _release_to_compact(r: Releases) -> dict:
    """Compact release representation for LLM context.

    Drops large/Trello-only fields to keep the tool result small.
    """
    return {
        "job": r.job,
        "release": r.release,
        "identifier": f"{r.job}-{r.release}",
        "project_name": r.job_name,
        "description": r.description,
        "fab_hrs": r.fab_hrs,
        "install_hrs": r.install_hrs,
        "paint_color": r.paint_color,
        "pm": r.pm,
        "drafter": r.by,
        "stage": r.stage,
        "stage_group": r.stage_group,
        "released_on": r.released.isoformat() if r.released else None,
        "start_install": r.start_install.isoformat() if r.start_install else None,
        "comp_eta": r.comp_eta.isoformat() if r.comp_eta else None,
        "installer": r.installer,
        "fab_order": r.fab_order,
        "is_active": r.is_active,
        "is_archived": r.is_archived,
        "notes": r.notes,
    }


def _parse_identifier(identifier: str):
    """Return (job:int, release:str|None) or (None, None) if unparseable.

    Accepts '410-271', '410 271', '410271', '410'.
    """
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
        # 5+ digits: first 3 are job number, remainder is release.
        if len(s) >= 5:
            return int(s[:3]), s[3:]
        return int(s), None

    return None, None


def search_jobs_by_identifier(identifier: str) -> dict[str, Any]:
    job, release = _parse_identifier(identifier)
    if job is None:
        return {
            "error": (
                f"Could not parse '{identifier}' as a job-release identifier. "
                "Try '410-271' or just '410'."
            ),
            "results": [],
        }

    q = Releases.query.filter(Releases.job == job)
    if release:
        q = q.filter(Releases.release == release)
    rows = q.order_by(Releases.release.asc()).limit(MAX_RESULTS).all()
    return {
        "query": {"job": job, "release": release},
        "result_count": len(rows),
        "results": [_release_to_compact(r) for r in rows],
    }


def search_jobs_by_project_name(query: str, limit: int = 20) -> dict[str, Any]:
    if not query or not query.strip():
        return {"error": "query is required", "results": []}
    limit = _clamp_limit(limit, default=20)
    pattern = f"%{query.strip()}%"
    rows = (
        Releases.query
        .filter(Releases.job_name.ilike(pattern))
        .order_by(Releases.job.asc(), Releases.release.asc())
        .limit(limit)
        .all()
    )
    return {
        "query": {"project_name_contains": query, "limit": limit},
        "result_count": len(rows),
        "results": [_release_to_compact(r) for r in rows],
    }


def get_release_history(job: int, release: str, max_events: int = 50,
                        include_system_echoes: bool = False) -> dict[str, Any]:
    """Audit trail for a single (job, release). Newest-first.

    Reuses `_extract_new_value_from_payload` so the human-readable summary
    matches the rest of the app. Joinedload on `User` keeps actor lookup O(1).
    """
    if job is None or release is None or str(release).strip() == "":
        return {"error": "both job and release are required", "events": []}
    try:
        job_int = int(job)
    except (TypeError, ValueError):
        return {"error": f"invalid job number: {job!r}", "events": []}
    release_str = str(release)
    max_events = _clamp_limit(max_events, default=50, ceiling=100)

    q = (
        ReleaseEvents.query
        .options(joinedload(ReleaseEvents.user))
        .filter(ReleaseEvents.job == job_int,
                ReleaseEvents.release == release_str)
    )
    if not include_system_echoes:
        q = q.filter(ReleaseEvents.is_system_echo == False)  # noqa: E712

    total = q.count()
    rows = q.order_by(ReleaseEvents.created_at.desc()).limit(max_events).all()

    events = []
    for ev in rows:
        actor_name = None
        if ev.user is not None:
            actor_name = ev.user.first_name or ev.user.username

        payload = ev.payload or {}
        from_value = payload.get("from") if isinstance(payload, dict) else None
        to_value = payload.get("to") if isinstance(payload, dict) else None

        events.append({
            "id": ev.id,
            "when": ev.created_at.isoformat() if ev.created_at else None,
            "applied_at": ev.applied_at.isoformat() if ev.applied_at else None,
            "action": ev.action,
            "summary": _extract_new_value_from_payload(ev.action, payload),
            "from": from_value,
            "to": to_value,
            "source": ev.source,
            "actor_name": actor_name,
            "actor_user_id": ev.internal_user_id,
            "external_actor": ev.external_user_id,
            "is_system_echo": ev.is_system_echo,
            "payload": payload,
        })

    return {
        "query": {
            "job": job_int,
            "release": release_str,
            "include_system_echoes": include_system_echoes,
        },
        "total_event_count": total,
        "returned_event_count": len(events),
        "events": events,
    }


def _coerce_job_release(job, release):
    """Return (job_int, release_str) or (None, None, error_dict)."""
    if job is None or release is None or str(release).strip() == "":
        return None, None, {"error": "both job and release are required"}
    try:
        job_int = int(job)
    except (TypeError, ValueError):
        return None, None, {"error": f"invalid job number: {job!r}"}
    return job_int, str(release).strip(), None


def _parse_iso_date(value, field: str):
    """Return (date, None) or (None, error_dict) for a YYYY-MM-DD string."""
    if not value or not str(value).strip():
        return None, {"error": f"{field} is required (YYYY-MM-DD)"}
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date(), None
    except ValueError:
        return None, {"error": f"invalid {field} {value!r}; expected YYYY-MM-DD"}


def get_release_pickup(job, release) -> dict[str, Any]:
    """Vendor pick-up order(s) (Dencol 'PU' email) for a release, newest first."""
    job_int, release_str, err = _coerce_job_release(job, release)
    if err:
        return {**err, "pickups": []}

    rec = Releases.query.filter_by(job=job_int, release=release_str).first()
    if rec is None:
        return {
            "error": f"no release {job_int}-{release_str} found",
            "pickups": [],
        }

    rows = (
        PickupOrder.query.filter_by(release_id=rec.id)
        .order_by(PickupOrder.created_at.desc())
        .all()
    )

    pickups = []
    for p in rows:
        body = p.email_body or ""
        truncated = len(body) > PICKUP_BODY_MAX_CHARS
        if truncated:
            body = body[:PICKUP_BODY_MAX_CHARS].rstrip() + "\n… (truncated)"
        pickups.append({
            "vendor": p.vendor,
            "email_subject": p.email_subject,
            "email_from": p.email_from,
            "email_to": p.email_to,
            "email_received_at": p.email_received_at.isoformat() if p.email_received_at else None,
            "email_body": body,
            "body_truncated": truncated,
            "trello_list_name": p.trello_list_name,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return {
        "identifier": f"{job_int}-{release_str}",
        "project_name": rec.job_name,
        "pickup_count": len(pickups),
        "pickups": pickups,
    }


def _conflict_to_compact(r: Releases) -> dict:
    start, end = release_window(r)
    return {
        "identifier": f"{r.job}-{r.release}",
        "project_name": r.job_name,
        "installer": r.installer,
        "start_install": start.isoformat() if start else None,
        "comp_eta": end.isoformat() if end else None,
    }


def propose_reschedule_install(job, release, new_start_install,
                               requested_installer=None,
                               new_comp_eta=None) -> dict[str, Any]:
    """READ-ONLY: validate a reschedule and report installer-team conflicts.

    Computes the proposed install window, checks the requested (or current)
    installer team for overlaps, and lists which teams are free. Makes no
    changes — the frontend confirmation card commits via /update-start-install.
    """
    job_int, release_str, err = _coerce_job_release(job, release)
    if err:
        return err

    rec = Releases.query.filter_by(job=job_int, release=release_str).first()
    if rec is None:
        return {"error": f"no release {job_int}-{release_str} found"}

    new_start, err = _parse_iso_date(new_start_install, "new_start_install")
    if err:
        return err

    cur_start = rec.start_install
    cur_end = rec.comp_eta

    # Proposed end date: explicit comp_eta wins; else preserve the current
    # install duration; else derive from install hours.
    if new_comp_eta:
        new_end, err = _parse_iso_date(new_comp_eta, "new_comp_eta")
        if err:
            return err
    elif cur_start and cur_end and cur_end >= cur_start:
        new_end = new_start + timedelta(days=(cur_end - cur_start).days)
    else:
        new_end = new_start + timedelta(days=default_window_days(rec.install_hrs))

    if new_end < new_start:
        return {"error": "completion date is before the start date"}

    current_team = (rec.installer or "").strip() or None
    requested = (requested_installer or "").strip() or current_team

    # Conflicts for the requested team in the proposed window (excluding self).
    conflicts = []
    if requested:
        conflicts = [
            _conflict_to_compact(r)
            for r in find_conflicts(
                requested, new_start, new_end,
                exclude_job=job_int, exclude_release=release_str,
            )
        ]

    # Availability across all configured teams.
    availability = team_availability(
        new_start, new_end,
        exclude_job=job_int, exclude_release=release_str,
    )
    free = [t for t, c in availability.items() if not c]
    busy = {
        t: [_conflict_to_compact(r) for r in c]
        for t, c in availability.items() if c
    }

    return {
        "job": job_int,
        "release": release_str,
        "identifier": f"{job_int}-{release_str}",
        "project_name": rec.job_name,
        "current": {
            "start_install": cur_start.isoformat() if cur_start else None,
            "comp_eta": cur_end.isoformat() if cur_end else None,
            "installer": current_team,
        },
        "proposed": {
            "start_install": new_start.isoformat(),
            "comp_eta": new_end.isoformat(),
            "installer": requested,
        },
        "requested_installer": requested,
        "has_conflict": bool(conflicts),
        "conflicts": conflicts,
        "free_teams": free,
        "busy_teams": busy,
        "all_teams": list(Config.INSTALLER_TEAMS),
    }


def _submittal_to_compact(s: Submittals) -> dict:
    today = date.today()
    days_since_bic_update = None
    if s.last_bic_update:
        days_since_bic_update = (datetime.utcnow() - s.last_bic_update).days

    lifespan_days = None
    if s.created_at:
        created_d = s.created_at.date() if hasattr(s.created_at, "date") else s.created_at
        lifespan_days = (today - created_d).days

    days_until_due = None
    if s.due_date:
        days_until_due = (s.due_date - today).days

    notes = s.notes
    if notes and len(notes) > 500:
        notes = notes[:500] + "…"

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
        "last_updated": s.last_updated.isoformat() if s.last_updated else None,
        "last_bic_update": s.last_bic_update.isoformat() if s.last_bic_update else None,
        "days_since_bic_update": days_since_bic_update,
        "lifespan_days": lifespan_days,
    }


def search_submittals(project_name: str | None = None,
                      project_number: str | None = None,
                      ball_in_court: str | None = None,
                      submittal_manager: str | None = None,
                      urgent_only: bool = False,
                      limit: int = 20) -> dict[str, Any]:
    """Submittals search with optional filters. At least one filter required.

    urgent_only=True restricts to submittals with order_number < 1 (excludes NULL)
    and sorts by order_number ascending so the most urgent come first.
    """
    if not (project_name or project_number or ball_in_court or submittal_manager or urgent_only):
        return {
            "error": "pass at least one filter (project_name, project_number, ball_in_court, submittal_manager, or urgent_only)",
            "results": [],
        }
    limit = _clamp_limit(limit, default=20, ceiling=100)

    q = Submittals.query
    if project_number:
        q = q.filter(Submittals.project_number == str(project_number))
    if project_name:
        q = q.filter(Submittals.project_name.ilike(f"%{project_name.strip()}%"))
    if ball_in_court:
        # ball_in_court is a comma-separated multi-assignee string
        # (see app/procore/helpers.py). Substring match handles partial names.
        q = q.filter(Submittals.ball_in_court.ilike(f"%{ball_in_court.strip()}%"))
    if submittal_manager:
        q = q.filter(Submittals.submittal_manager.ilike(f"%{submittal_manager.strip()}%"))
    if urgent_only:
        q = q.filter(Submittals.order_number < 1)

    if urgent_only:
        q = q.order_by(Submittals.order_number.asc().nullslast(),
                       Submittals.last_updated.desc())
    else:
        q = q.order_by(Submittals.last_updated.desc().nullslast(),
                       Submittals.created_at.desc())

    rows = q.limit(limit).all()

    return {
        "query": {
            "project_name": project_name,
            "project_number": project_number,
            "ball_in_court": ball_in_court,
            "submittal_manager": submittal_manager,
            "urgent_only": urgent_only,
            "limit": limit,
        },
        "result_count": len(rows),
        "results": [_submittal_to_compact(s) for s in rows],
    }


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
        item = {
            "id": n.id,
            "type": n.type,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        if n.board_item is not None:
            item["board_item"] = {
                "id": n.board_item.id,
                "title": n.board_item.title,
                "category": n.board_item.category,
                "status": n.board_item.status,
                "priority": n.board_item.priority,
            }
        if n.submittal is not None:
            item["submittal"] = {
                "submittal_id": n.submittal.submittal_id,
                "title": n.submittal.title,
                "project_number": n.submittal.project_number,
                "project_name": n.submittal.project_name,
                "status": n.submittal.status,
                "ball_in_court": n.submittal.ball_in_court,
            }
        results.append(item)

    return {
        "query": {"unread_only": unread_only, "limit": limit},
        "result_count": len(results),
        "results": results,
    }


def _call_gmail(action: str, user_id, fn, *args, **kwargs):
    """Run a Gmail-touching call, mapping known auth/scope errors to dicts."""
    try:
        return fn(*args, **kwargs)
    except GmailScopeError as exc:
        return {"error": str(exc), "needs_reconnect": True}
    except GoogleAuthError as exc:
        return {"error": f"gmail auth failed: {exc}", "needs_reconnect": True}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"banana_boy_{action}_failed", user_id=user_id, error=str(exc))
        return {"error": f"could not {action.replace('_', ' ')}: {exc}"}


def create_email_draft_tool(context: dict, to: str, subject: str, body: str,
                            cc: str | None = None, bcc: str | None = None) -> dict[str, Any]:
    user_id = context.get("user_id")
    if not user_id:
        return {"error": "no signed-in user"}
    if not to or not to.strip():
        return {"error": "recipient (to) is required"}

    result = _call_gmail(
        "create_draft", user_id, create_draft,
        user_id, to.strip(), subject or "", body or "", cc=cc, bcc=bcc,
    )
    if "error" in result:
        return result

    logger.info(
        "banana_boy_draft_created",
        user_id=user_id, draft_id=result.get("draft_id"), to=to, subject=subject,
    )
    return {
        "draft_id": result["draft_id"],
        "to": result["to"],
        "subject": result["subject"],
        "snippet": result["snippet"],
        "instructions": (
            "Summarize this draft to the user (to, subject, body) and ask "
            "them to confirm before calling send_email_draft."
        ),
    }


def send_email_draft_tool(context: dict, draft_id: str) -> dict[str, Any]:
    user_id = context.get("user_id")
    if not user_id:
        return {"error": "no signed-in user"}
    if not draft_id:
        return {"error": "draft_id is required"}

    result = _call_gmail("send_draft", user_id, send_draft, user_id, draft_id)
    if "error" in result:
        return result

    logger.info(
        "banana_boy_draft_sent",
        user_id=user_id, draft_id=draft_id, message_id=result.get("message_id"),
    )
    return result


def scan_drawing_compliance(context: dict, job: int, release: str) -> dict[str, Any]:
    """Sub-agent compliance scan for a release's fab PDF.

    Loads `{job}-{release}-fc.pdf` via the registered DrawingLoader and
    fires a Sonnet vision call with the PDF + Division 05 KB. The Sonnet
    call's tokens, duration, and cost are appended to `context["usage_sink"]`
    when present so the chat route can persist them alongside the Haiku turn.
    """
    if job is None or release is None or str(release).strip() == "":
        return {"error": "both job and release are required"}

    loader = current_app.extensions.get(DRAWING_LOADER_KEY)
    if loader is None:
        return {"error": "drawing loader is not configured"}

    loaded = loader.load(job, release)
    if loaded is None:
        return {
            "error": f"no fab drawing on file for {job}-{release}",
            "expected_filename": f"{job}-{release}-fc.pdf",
        }
    pdf_bytes, source_meta = loaded

    findings = scan_pdf(
        pdf_bytes, job, release,
        usage_sink=context.get("usage_sink"),
    )
    logger.info(
        "banana_boy_compliance_scan",
        job=job, release=release, source=source_meta.get("source"),
        size_bytes=source_meta.get("size_bytes"),
    )
    return {
        "job": job,
        "release": release,
        "source": source_meta,
        "findings": findings,
        "model": "claude-sonnet-4-6",
    }


def list_drawing_versions(job: int, release: str) -> dict[str, Any]:
    """Return the marked-up drawing version history for a release.

    Read-only; safe to call without a signed-in user. Skips soft-deleted rows
    and orders newest-first.
    """
    if job is None or release is None or str(release).strip() == "":
        return {"error": "both job and release are required"}

    release_row = Releases.query.filter_by(job=job, release=str(release)).first()
    if release_row is None:
        return {"error": f"no release on file for {job}-{release}"}

    versions = (
        ReleaseDrawingVersion.query
        .filter_by(release_id=release_row.id, is_deleted=False)
        .order_by(ReleaseDrawingVersion.version_number.desc())
        .all()
    )

    out = []
    for idx, v in enumerate(versions):
        uploaded_by_name = None
        if v.uploaded_by is not None:
            first = (v.uploaded_by.first_name or "").strip()
            last = (v.uploaded_by.last_name or "").strip()
            uploaded_by_name = (f"{first} {last}".strip()) or v.uploaded_by.username
        out.append({
            "version_number": v.version_number,
            "uploaded_by": uploaded_by_name,
            "uploaded_at": v.uploaded_at.isoformat() if v.uploaded_at else None,
            "note": v.note,
            "source_version_id": v.source_version_id,
            "is_latest": idx == 0,
        })

    return {"job": job, "release": release, "versions": out}


def scan_markup_diff(context: dict, job: int, release: str,
                     from_version: int | None = None,
                     to_version: int | None = None) -> dict[str, Any]:
    """Sub-agent diff scan over two marked-up drawing versions.

    Defaults to (latest, latest.source_version_id-or-previous). Loads both PDF
    blobs from storage, fires a Sonnet vision call, and appends one usage
    record to `context["usage_sink"]` when present.
    """
    from app.brain.job_log.features.pdf_markup.storage import read_pdf

    if job is None or release is None or str(release).strip() == "":
        return {"error": "both job and release are required"}

    release_row = Releases.query.filter_by(job=job, release=str(release)).first()
    if release_row is None:
        return {"error": f"no release on file for {job}-{release}"}

    versions = (
        ReleaseDrawingVersion.query
        .filter_by(release_id=release_row.id, is_deleted=False)
        .order_by(ReleaseDrawingVersion.version_number.desc())
        .all()
    )
    if len(versions) < 2:
        return {
            "error": (
                f"{job}-{release} needs at least two drawing versions to diff "
                f"(found {len(versions)})"
            ),
        }

    by_number = {v.version_number: v for v in versions}
    latest = versions[0]

    to_v = by_number.get(to_version) if to_version is not None else latest
    if to_v is None:
        return {"error": f"version {to_version} not found for {job}-{release}"}

    if from_version is not None:
        from_v = by_number.get(from_version)
        if from_v is None:
            return {"error": f"version {from_version} not found for {job}-{release}"}
    elif to_v.source_version_id is not None:
        from_v = next(
            (v for v in versions if v.id == to_v.source_version_id),
            None,
        )
        if from_v is None:
            from_v = next(
                (v for v in versions if v.version_number < to_v.version_number),
                None,
            )
    else:
        from_v = next(
            (v for v in versions if v.version_number < to_v.version_number),
            None,
        )

    if from_v is None or from_v.id == to_v.id:
        return {
            "error": (
                f"could not find an earlier version to diff against v{to_v.version_number} "
                f"for {job}-{release}"
            ),
        }

    try:
        from_bytes = read_pdf(from_v.storage_key)
        to_bytes = read_pdf(to_v.storage_key)
    except FileNotFoundError as exc:
        return {"error": f"drawing version blob missing: {exc}"}

    findings = scan_markup_diff_pdfs(
        from_bytes=from_bytes,
        to_bytes=to_bytes,
        job=job,
        release=release,
        from_version=from_v.version_number,
        to_version=to_v.version_number,
        usage_sink=context.get("usage_sink"),
    )
    logger.info(
        "banana_boy_markup_diff_scan",
        job=job, release=release,
        from_version=from_v.version_number,
        to_version=to_v.version_number,
    )
    return {
        "job": job,
        "release": release,
        "from_version": from_v.version_number,
        "to_version": to_v.version_number,
        "findings": findings,
        "model": "claude-sonnet-4-6",
    }


# Tools that receive the per-request `context` dict (user_id, usage_sink, ...)
# as their first positional argument.
USER_SCOPED_TOOLS = {
    TOOL_NOTIFICATIONS,
    TOOL_CREATE_DRAFT,
    TOOL_SEND_DRAFT,
    TOOL_SCAN_COMPLIANCE,
    TOOL_SCAN_MARKUP_DIFF,
}

TOOL_EXECUTORS = {
    TOOL_SEARCH_BY_ID: search_jobs_by_identifier,
    TOOL_SEARCH_BY_NAME: search_jobs_by_project_name,
    TOOL_RELEASE_HISTORY: get_release_history,
    TOOL_SEARCH_SUBMITTALS: search_submittals,
    TOOL_NOTIFICATIONS: get_my_notifications,
    TOOL_CREATE_DRAFT: create_email_draft_tool,
    TOOL_SEND_DRAFT: send_email_draft_tool,
    TOOL_SCAN_COMPLIANCE: scan_drawing_compliance,
    TOOL_LIST_DRAWING_VERSIONS: list_drawing_versions,
    TOOL_SCAN_MARKUP_DIFF: scan_markup_diff,
    TOOL_GET_PICKUP: get_release_pickup,
    TOOL_PROPOSE_RESCHEDULE: propose_reschedule_install,
}


def execute_tool(name: str, arguments: dict, context: dict | None = None) -> dict[str, Any]:
    """Dispatch a tool call by name. Returns a JSON-serializable dict.

    `context` is supplied by the chat client — typically `{"user_id": <id>}`.
    User-scoped tools (`USER_SCOPED_TOOLS`) receive it as their first arg.
    """
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
        logger.error("banana_boy_tool_failed", tool=name, error=str(exc))
        # Tool DB queries can leave the session in an aborted state; reset so
        # the next request doesn't inherit a poisoned transaction.
        db.session.rollback()
        return {"error": f"tool {name} failed: {exc}"}
