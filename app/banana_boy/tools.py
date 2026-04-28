"""Tool implementations Banana Boy can invoke via Anthropic tool-use.

Each tool has:
  - a JSON-Schema definition exposed to Claude (`TOOL_DEFINITIONS`)
  - a Python executor mapped by name in `TOOL_EXECUTORS`

User-scoped tools read `context["user_id"]` rather than trusting any
user-supplied identifier — never let the LLM pretend to be a different user.
"""
import re
from typing import Any

from sqlalchemy.orm import joinedload

from app.auth.google_tokens import GoogleAuthError
from app.banana_boy.gmail_client import GmailScopeError, create_draft, send_draft
from app.history import _extract_new_value_from_payload
from app.logging_config import get_logger
from app.models import Notification, ReleaseEvents, Releases, db

logger = get_logger(__name__)

TOOL_SEARCH_BY_ID = "search_jobs_by_identifier"
TOOL_SEARCH_BY_NAME = "search_jobs_by_project_name"
TOOL_RELEASE_HISTORY = "get_release_history"
TOOL_CREATE_DRAFT = "create_email_draft"
TOOL_SEND_DRAFT = "send_email_draft"
TOOL_NOTIFICATIONS = "get_my_notifications"

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


USER_SCOPED_TOOLS = {
    TOOL_NOTIFICATIONS,
    TOOL_CREATE_DRAFT,
    TOOL_SEND_DRAFT,
}

TOOL_EXECUTORS = {
    TOOL_SEARCH_BY_ID: search_jobs_by_identifier,
    TOOL_SEARCH_BY_NAME: search_jobs_by_project_name,
    TOOL_RELEASE_HISTORY: get_release_history,
    TOOL_NOTIFICATIONS: get_my_notifications,
    TOOL_CREATE_DRAFT: create_email_draft_tool,
    TOOL_SEND_DRAFT: send_email_draft_tool,
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
