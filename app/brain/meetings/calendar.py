"""Calendar → Recall scheduling (app-only Graph).

The calendar IS the scheduling UI: invite the configured mailbox (e.g.
bb@mhmw.com) to a Teams meeting and a Recall notetaker bot ("BB") joins on its
own at the event's start time. We read the mailbox's calendar *as the
application* (app-only Graph, scoped by an ApplicationAccessPolicy), so no user
logs in and nothing is opened org-wide.

We deliberately do NOT use Recall's own Calendar-V2 integration: that would mean
connecting bb's calendar to Recall via delegated OAuth (re-introducing the
consent/exposure wall the app-only approach exists to avoid). Instead we poll
Graph ourselves and dispatch bots directly.

Flow per poll (every RECALL_CALENDAR_POLL_MINUTES):
  1. `calendarView` over [now − overlap, now + lookahead] — expands recurrences
     into concrete instances, so each occurrence is handled on its own.
  2. For each event, reconcile against any meeting we already scheduled for it
     (idempotent on the Graph event id):
       - new + has a Teams join URL + not cancelled/declined → schedule a bot
         with join_at = start (Recall guarantees on-time join when join_at is
         ≥10 min out; nearer/started meetings join ad-hoc immediately);
       - already scheduled but the event was cancelled/declined → cancel the bot;
       - already scheduled but the start moved → cancel + re-dispatch at the new
         time. Only ever reconcile a bot still in 'scheduled' — once it's live
         (joining/recording/done) we leave it alone.
"""
import re
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
CALENDAR_SELECT = (
    "id,subject,start,end,isCancelled,isOnlineMeeting,onlineMeeting,"
    "onlineMeetingUrl,responseStatus,bodyPreview"
)
# Look slightly into the past so a just-started meeting (and late cancellations of
# imminent events) are still caught; calendarView returns events overlapping the window.
WINDOW_BACK = timedelta(minutes=5)
# A Teams join link anywhere in the event body, as a last resort when the structured
# onlineMeeting fields are absent (e.g. a link pasted into the invite body).
_TEAMS_LINK_RE = re.compile(r"https://teams\.microsoft\.com/l/meetup-join/\S+")
# Bot lifecycle states we may still reconcile (cancel / move). Once a bot is live we
# never touch it — anything not 'scheduled' is left alone.
_RECONCILABLE = {"scheduled"}


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
    """Teams join URL for an event, or None if it isn't an online Teams meeting.

    Prefers the structured onlineMeeting.joinUrl, then onlineMeetingUrl, then a
    Teams link pasted into the body preview.
    """
    online = event.get("onlineMeeting") or {}
    url = online.get("joinUrl") or event.get("onlineMeetingUrl")
    if url:
        return url.strip()
    match = _TEAMS_LINK_RE.search(event.get("bodyPreview") or "")
    return match.group(0) if match else None


def _is_declined(event):
    return ((event.get("responseStatus") or {}).get("response")) == "declined"


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


def _join_at_for(starts_at, now, lead):
    """When to tell Recall to join: start − lead, or None (join now) if that's past."""
    join_at = starts_at - lead
    return join_at if join_at > now else None


def _handle_event(event, now, lead, dry_run):
    """Reconcile one calendar event with our scheduling state.

    Returns one of: 'scheduled' | 'rescheduled' | 'cancelled' | 'skipped'.
    """
    event_id = event.get("id")
    if not event_id:
        return "skipped"

    existing = Meeting.query.filter_by(calendar_event_id=event_id).first()
    cancelled = bool(event.get("isCancelled")) or _is_declined(event)
    join_url = _join_url(event)
    starts_at = _parse_graph_dt(event.get("start"))

    # --- Already scheduled: reconcile cancel / move (only while still 'scheduled') ---
    if existing is not None:
        if existing.bot_status not in _RECONCILABLE:
            return "skipped"  # bot is live or finished — hands off
        if cancelled:
            if not dry_run:
                recall.delete_bot(existing.recall_bot_id)
                existing.bot_status = "cancelled"
                db.session.commit()
            logger.info("calendar_recall_cancelled", event_id=event_id,
                        bot_id=existing.recall_bot_id, dry_run=dry_run)
            return "cancelled"
        if starts_at and existing.occurred_at != starts_at and join_url:
            # Meeting moved — retract the old bot and dispatch one for the new time.
            if not dry_run:
                deleted = recall.delete_bot(existing.recall_bot_id)
                if not deleted:
                    return "skipped"  # bot already joining; can't move it
                try:
                    bot_id = recall.dispatch_bot(
                        join_url, join_at=_join_at_for(starts_at, now, lead))
                except recall.RecallError as exc:
                    logger.warning("calendar_recall_reschedule_dispatch_failed",
                                   event_id=event_id, error=str(exc))
                    return "skipped"
                existing.recall_bot_id = bot_id
                existing.occurred_at = starts_at
                existing.meeting_url = join_url[:1000]
                db.session.commit()
            logger.info("calendar_recall_rescheduled", event_id=event_id,
                        starts_at=starts_at.isoformat(), dry_run=dry_run)
            return "rescheduled"
        return "skipped"  # unchanged

    # --- New event: schedule a bot if it's a live, joinable, future Teams meeting ---
    if cancelled or not join_url or starts_at is None:
        return "skipped"
    if not dry_run:
        try:
            bot_id = recall.dispatch_bot(join_url, join_at=_join_at_for(starts_at, now, lead))
        except recall.RecallError as exc:
            logger.warning("calendar_recall_dispatch_failed", event_id=event_id, error=str(exc))
            return "skipped"
        service.create_scheduled_recall_meeting(
            meeting_url=join_url,
            bot_id=bot_id,
            calendar_event_id=event_id,
            starts_at=starts_at,
            title=event.get("subject") or "Scheduled meeting",
            agenda_text=(event.get("bodyPreview") or "").strip() or None,
        )
    logger.info("calendar_recall_scheduled", event_id=event_id,
                starts_at=starts_at.isoformat(), dry_run=dry_run)
    return "scheduled"


def poll(dry_run=False):
    """Scan the configured mailbox's calendar and reconcile Recall bots.

    Idempotent and safe to run on a schedule — an unchanged, already-scheduled event
    is a no-op. With dry_run=True, classifies every event and reports the action it
    WOULD take without dispatching/cancelling anything (for live testing).

    Returns a summary dict {mailbox, events, scheduled, rescheduled, cancelled, skipped}.
    """
    cfg = current_app.config
    mailbox = cfg.get("RECALL_CALENDAR_MAILBOX", "bb@mhmw.com")
    lookahead = timedelta(minutes=cfg.get("RECALL_CALENDAR_LOOKAHEAD_MINUTES", 60))
    lead = timedelta(seconds=cfg.get("RECALL_CALENDAR_JOIN_LEAD_SECONDS", 60))

    now = datetime.utcnow()
    events = list_upcoming_events(mailbox, now - WINDOW_BACK, now + lookahead)

    counts = {"scheduled": 0, "rescheduled": 0, "cancelled": 0, "skipped": 0}
    for event in events:
        counts[_handle_event(event, now, lead, dry_run)] += 1

    summary = {"mailbox": mailbox, "events": len(events), "dry_run": dry_run, **counts}
    logger.info("calendar_recall_poll", **summary)
    return summary
