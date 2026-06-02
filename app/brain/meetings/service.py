"""Meeting → checklist service: create+extract, review (yes/no/edit), notify owners.

Kept as plain service functions (the routes delegate here), mirroring the brain
feature-command split without the event/outbox machinery — checklist items are not
release-scoped and have no async external push.
"""
import re
from datetime import date, datetime, timedelta

from app.config import Config as cfg
from app.logging_config import get_logger
from app.models import (
    db, Meeting, ChecklistItem, Releases, Submittals, User, Notification,
)
from app.brain.meetings.extract import extract_items, VALID_TYPES

logger = get_logger(__name__)

NOTIFY_LEAD_DAYS = 2       # ping when the due date is within this many days
NOTIFY_DEDUP_HOURS = 20    # don't re-ping the same item within this window
_EDITABLE = ("title", "detail", "item_type", "gc_facing", "owner_user_id",
             "due_date", "release_id", "submittal_id")


def get_reviewer():
    """The user who reviews post-meeting checklists (MVP: Bill, by config)."""
    return User.query.filter_by(username=cfg.CHECKLIST_REVIEWER_USERNAME).first()


def _resolve_owner_id(owner_name):
    if not owner_name:
        return None
    u = User.query.filter(
        db.func.lower(User.first_name) == str(owner_name).strip().lower(),
        User.is_active.is_(True),
    ).first()
    return u.id if u else None


def _parse_due(value):
    if not value or isinstance(value, date):
        return value or None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _resolve_release(ref):
    """'480-146' -> (Releases.id, job_number_str); best-effort."""
    if not ref:
        return None, None
    m = re.match(r"\s*(\d+)\s*-\s*(\w+)\s*$", str(ref))
    if not m:
        return None, None
    job, rel = int(m.group(1)), m.group(2)
    row = Releases.query.filter_by(job=job, release=rel).first()
    return (row.id, str(job)) if row else (None, None)


def _resolve_submittal(ref):
    if not ref:
        return None
    row = Submittals.query.filter_by(submittal_id=str(ref)).first()
    return row.submittal_id if row else None


def create_meeting_with_extraction(*, title, meeting_type, transcript,
                                   project_number=None, occurred_at=None,
                                   created_by_id=None):
    """Create a Meeting, mine the transcript into proposed ChecklistItems, and
    notify the reviewer. Returns the Meeting."""
    # Run the (slow, external) extraction BEFORE opening the write transaction —
    # holding a DB transaction across the LLM HTTP call resets the connection and
    # corrupts the unit of work.
    raw_items = extract_items(transcript)

    meeting = Meeting(
        title=(title or "Untitled meeting")[:255],
        meeting_type=meeting_type or "other",
        source="stub",
        project_number=project_number,
        occurred_at=occurred_at,
        transcript=transcript,
        created_by=created_by_id,
    )
    db.session.add(meeting)
    db.session.flush()  # assign meeting.id

    created = 0
    for it in raw_items:
        itype = it.get("item_type") if it.get("item_type") in VALID_TYPES else "action"
        rel_id, rel_proj = _resolve_release(it.get("release_ref"))
        db.session.add(ChecklistItem(
            meeting_id=meeting.id,
            title=((it.get("title") or "").strip()[:1000]) or "(untitled)",
            detail=it.get("detail"),
            item_type=itype,
            gc_facing=bool(it.get("gc_facing")),
            proposed_owner_user_id=_resolve_owner_id(it.get("owner_name")),
            proposed_due_date=_parse_due(it.get("due_date")),
            confidence=it.get("confidence"),
            release_id=rel_id,
            submittal_id=_resolve_submittal(it.get("submittal_ref")),
        ))
        created += 1
        if rel_proj and not meeting.project_number:
            meeting.project_number = rel_proj

    meeting.extracted_at = datetime.utcnow()
    db.session.commit()

    _notify_reviewer(meeting, created)
    logger.info("meeting_ingested", meeting_id=meeting.id, items=created,
                meeting_type=meeting.meeting_type)
    return meeting


def _notify_reviewer(meeting, n_items):
    reviewer = get_reviewer()
    if not reviewer:
        logger.warning("checklist_reviewer_unresolved",
                       username=cfg.CHECKLIST_REVIEWER_USERNAME)
        return
    db.session.add(Notification(
        user_id=reviewer.id,
        type="checklist_ready",
        message=f'Post-meeting checklist ready: {n_items} item(s) from "{meeting.title}"',
    ))
    db.session.commit()


def review_item(item_id, *, action=None, fields=None, reviewer=None):
    """Apply edits and/or an action (accept/reject/done) to a checklist item.

    On accept, owner + due default to the agent's proposal when the reviewer didn't
    override them — but the reviewer always has final say via `fields`.
    """
    item = db.session.get(ChecklistItem, item_id)
    if not item:
        return None
    fields = fields or {}

    for f in _EDITABLE:
        if f in fields:
            val = fields[f]
            if f == "due_date":
                val = _parse_due(val)
            setattr(item, f, val)

    if action == "accept":
        if item.owner_user_id is None:
            item.owner_user_id = item.proposed_owner_user_id
        if item.due_date is None:
            item.due_date = item.proposed_due_date
        item.status = "accepted"
    elif action == "reject":
        item.status = "rejected"
    elif action == "done":
        item.status = "done"

    if action:
        item.reviewed_by = reviewer.id if reviewer else None
        item.reviewed_at = datetime.utcnow()

    db.session.commit()
    return item


def notify_due_items(today=None):
    """Ping owners of accepted items whose due date is near/overdue (deduped).
    Returns the number of notifications sent. Safe to run on a schedule."""
    today = today or date.today()
    cutoff = today + timedelta(days=NOTIFY_LEAD_DAYS)
    dedup_before = datetime.utcnow() - timedelta(hours=NOTIFY_DEDUP_HOURS)

    items = ChecklistItem.query.filter(
        ChecklistItem.status == "accepted",
        ChecklistItem.owner_user_id.isnot(None),
        ChecklistItem.due_date.isnot(None),
        ChecklistItem.due_date <= cutoff,
    ).all()

    sent = 0
    for item in items:
        if item.last_notified_at and item.last_notified_at > dedup_before:
            continue
        when = "overdue" if item.due_date < today else f"due {item.due_date.isoformat()}"
        db.session.add(Notification(
            user_id=item.owner_user_id,
            type="checklist_due",
            message=f"To-do {when}: {item.title[:160]}",
            checklist_item_id=item.id,
        ))
        item.last_notified_at = datetime.utcnow()
        sent += 1
    if sent:
        db.session.commit()
    logger.info("checklist_due_scan", sent=sent, candidates=len(items))
    return sent
