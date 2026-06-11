"""Calendar → Recall scheduling (app-only Graph).

The calendar IS the scheduling UI: invite the configured mailbox (e.g.
bb@mhmw.com) to a Teams meeting and this poller schedules a Recall notetaker bot
to join at the event's start time. Reads the mailbox's calendar *as the
application* (app-only Graph, scoped by an ApplicationAccessPolicy), so no user
logs in and nothing is opened org-wide.

Flow per poll (every RECALL_CALENDAR_POLL_MINUTES):
  1. `calendarView` over [now, now + lookahead] — expands recurrences into
     concrete instances, so each occurrence is handled on its own.
  2. Keep events that carry a Teams join URL.
  3. For each one not already scheduled (idempotent on the Graph event id),
     dispatch a Recall bot with `join_at` = start (minus a small lead) and
     persist a `source='recall'`, `bot_status='scheduled'` meeting.

`join_at` lets us dispatch as soon as the event appears — Recall holds the bot
until the meeting starts — so the poll only needs to run more often than the
lookahead window is wide.
"""
from datetime import datetime, timedelta

from flask import current_app

from app.brain.meetings import recall, service
from app.logging_config import get_logger
from app.microsoft.graph_app_client import graph_get
from app.models import Meeting, db

logger = get_logger(__name__)

# Ask Graph to return all event times in UTC so we can parse them as naive UTC
# (the convention the rest of the app stores datetimes in).
_UTC_PREFER = {"Prefer": 'outlook.timezone="UTC"'}
CALENDAR_SELECT = "id,subject,start,end,isOnlineMeeting,onlineMeeting,bodyPreview"


def _parse_graph_dt(node):
    """Graph dateTimeTimeZone ({dateTime, timeZone}) → naive UTC datetime.

    With the outlook.timezone="UTC" Prefer header the value is already UTC, so we
    drop any tz and the fractional seconds Graph appends.
    """
    if not node:
        return None
    value = node.get("dateTime") if isinstance(node, dict) else node
    if not value:
        return None
    try:
        # e.g. '2026-06-12T18:30:00.0000000' — trim to seconds, treat as UTC.
        return datetime.fromisoformat(value[:19])
    except (ValueError, TypeError):
        return None


def _join_url(event):
    """Teams join URL for an event, or None if it isn't an online Teams meeting."""
    online = event.get("onlineMeeting") or {}
    url = online.get("joinUrl")
    return url.strip() if url else None


def list_upcoming_events(mailbox, window_start, window_end):
    """Graph calendarView for `mailbox` over [window_start, window_end] (naive UTC).

    Returns the raw event dicts (recurrences already expanded into instances).
    """
    params = {
        "startDateTime": window_start.replace(microsecond=0).isoformat() + "Z",
        "endDateTime": window_end.replace(microsecond=0).isoformat() + "Z",
        "$select": CALENDAR_SELECT,
        "$orderby": "start/dateTime",
        "$top": 50,
    }
    events = []
    path = f"/users/{mailbox}/calendarView"
    while path:
        data = graph_get(path, params=params, headers=_UTC_PREFER)
        events.extend(data.get("value", []) or [])
        path = data.get("@odata.nextLink")
        params = None  # nextLink already carries the query
    return events


def _already_scheduled(event_id):
    return db.session.query(
        Meeting.query.filter_by(calendar_event_id=event_id).exists()
    ).scalar()


def _schedule_event(event, now, lead):
    """Dispatch a bot for one calendar event and persist its meeting.

    Returns 'scheduled' | 'skipped' | 'failed'. Idempotent: an event already tied
    to a meeting is skipped.
    """
    event_id = event.get("id")
    join_url = _join_url(event)
    if not event_id or not join_url:
        return "skipped"
    if _already_scheduled(event_id):
        return "skipped"

    starts_at = _parse_graph_dt(event.get("start"))
    if starts_at is None:
        logger.warning("calendar_event_no_start", event_id=event_id)
        return "skipped"

    # Future start → schedule a join a touch early. Already-running meeting (start
    # in the past but still inside the window) → join now (join_at=None).
    join_at = starts_at - lead
    if join_at <= now:
        join_at = None

    try:
        bot_id = recall.dispatch_bot(join_url, join_at=join_at)
    except recall.RecallError as exc:
        logger.warning("calendar_recall_dispatch_failed", event_id=event_id, error=str(exc))
        return "failed"

    service.create_scheduled_recall_meeting(
        meeting_url=join_url,
        bot_id=bot_id,
        calendar_event_id=event_id,
        starts_at=starts_at,
        title=event.get("subject") or "Scheduled meeting",
        agenda_text=(event.get("bodyPreview") or "").strip() or None,
    )
    logger.info("calendar_recall_scheduled", event_id=event_id, bot_id=bot_id,
                starts_at=starts_at.isoformat())
    return "scheduled"


def poll():
    """Scan the configured mailbox's calendar and schedule bots for new meetings.

    Returns a summary dict. Safe to call on a schedule and idempotent — an event
    already scheduled is skipped, so overlapping windows land 0 new bots.
    """
    cfg = current_app.config
    mailbox = cfg.get("RECALL_CALENDAR_MAILBOX", "bb@mhmw.com")
    lookahead = timedelta(minutes=cfg.get("RECALL_CALENDAR_LOOKAHEAD_MINUTES", 60))
    lead = timedelta(seconds=cfg.get("RECALL_CALENDAR_JOIN_LEAD_SECONDS", 60))

    now = datetime.utcnow()
    events = list_upcoming_events(mailbox, now, now + lookahead)

    counts = {"scheduled": 0, "skipped": 0, "failed": 0}
    for event in events:
        counts[_schedule_event(event, now, lead)] += 1

    logger.info("calendar_recall_poll", mailbox=mailbox, events=len(events), **counts)
    return {"mailbox": mailbox, "events": len(events), **counts}
