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
from app.brain.meetings.extract import extract, VALID_TYPES

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


def _end_of_week(today=None):
    """End of the current work week (Friday). Returns today if it's already Friday;
    rolls to next Friday on the weekend. Used as the default due date when the meeting
    didn't state one — so every to-do gets a deadline to drive the reminder scan."""
    today = today or date.today()
    return today + timedelta(days=(4 - today.weekday()) % 7)  # Mon=0 … Fri=4


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


def extract_into_meeting(meeting, *, regenerate=False, notify=True):
    """Mine the meeting's stored transcript into proposed ChecklistItems.

    Shared by the paste-ingest flow and the on-demand "Generate to-do list" button.
    The meeting must already be persisted (committed) so the LLM call isn't made with
    an open write transaction. With regenerate=True, prior items are cleared first.
    Returns the number of items created.
    """
    if regenerate:
        ChecklistItem.query.filter_by(meeting_id=meeting.id).delete()
        db.session.commit()

    # Give the extractor the team roster so owner_name maps to real users.
    people = [u.first_name for u in User.query.filter_by(is_active=True).all()
              if u.first_name]
    result = extract(meeting.transcript or "", people=people)
    raw_items = result["items"]
    usage = result["usage"]

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
            # Default to end of the current week when the meeting didn't state a date.
            proposed_due_date=_parse_due(it.get("due_date")) or _end_of_week(),
            # confidence is reused for the owner-match score, set by the matcher below.
            confidence=None,
            release_id=rel_id,
            submittal_id=_resolve_submittal(it.get("submittal_ref")),
        ))
        created += 1
        if rel_proj and not meeting.project_number:
            meeting.project_number = rel_proj

    meeting.extracted_at = datetime.utcnow()
    db.session.commit()

    # Infer owners for the items no one was named on — match each to an active job and
    # lift the PM / submittal manager. Haiku usage folds into the meeting cost meter.
    from app.brain.meetings import owner_match
    match_usage = owner_match.infer_owners_for_meeting(meeting)
    blended = bool(match_usage.get("cost_usd"))
    meeting.extract_model = usage["model"] + (" +haiku" if blended else "")
    meeting.extract_input_tokens = (usage["input_tokens"] or 0) + (match_usage.get("input_tokens") or 0)
    meeting.extract_output_tokens = (usage["output_tokens"] or 0) + (match_usage.get("output_tokens") or 0)
    meeting.extract_cost_usd = round((usage["cost_usd"] or 0) + (match_usage.get("cost_usd") or 0), 6)
    db.session.commit()

    if notify:
        _notify_reviewer(meeting, created)
    logger.info("meeting_extracted", meeting_id=meeting.id, items=created)
    return created


def create_meeting_with_extraction(*, title, meeting_type, transcript,
                                   project_number=None, occurred_at=None,
                                   created_by_id=None):
    """Create a Meeting from a pasted transcript and build its checklist. Returns the
    Meeting. Commits the meeting before extraction so the LLM call never runs inside
    an open write transaction (which would reset the connection)."""
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
    db.session.commit()  # persist before the (slow, external) extraction
    extract_into_meeting(meeting)
    return meeting


def create_manual_meeting(*, title, meeting_type, transcript, created_by_id=None):
    """Create a meeting from a pasted transcript WITHOUT extracting — the checklist is
    generated on demand via the 'Generate to-do list' button (so the transcript goes
    straight to the LLM only when the reviewer asks). Returns the Meeting."""
    meeting = Meeting(
        title=(title or "Pasted meeting")[:255],
        meeting_type=meeting_type or "other",
        source="manual",
        transcript=transcript,
        occurred_at=datetime.utcnow(),
        created_by=created_by_id,
    )
    db.session.add(meeting)
    db.session.commit()
    logger.info("manual_meeting_created", meeting_id=meeting.id,
                chars=len(transcript or ""))
    return meeting


def create_recall_meeting(*, meeting_url, bot_id, title=None, meeting_type=None,
                          created_by_id=None):
    """Persist a meeting whose transcript will come from a Recall bot.

    Immediate-send MVP: the bot joins now, so occurred_at is stamped now. No
    transcript/extraction yet — that arrives via the pull step. bot_status starts at
    'joining' and is kept fresh by the recall-webhook receiver.
    """
    meeting = Meeting(
        title=(title or "Recall meeting")[:255],
        meeting_type=meeting_type or "other",
        source="recall",
        meeting_url=(meeting_url or "")[:1000] or None,
        recall_bot_id=bot_id,
        bot_status="joining",
        occurred_at=datetime.utcnow(),
        created_by=created_by_id,
    )
    db.session.add(meeting)
    db.session.commit()
    logger.info("recall_meeting_created", meeting_id=meeting.id, bot_id=bot_id)
    return meeting


def update_bot_status(bot_id, status_code):
    """Update the bot_status of the meeting tied to a Recall bot id. Idempotent;
    no-op if the bot id isn't ours or the status is unchanged. Returns the Meeting."""
    if not bot_id or not status_code:
        return None
    meeting = Meeting.query.filter_by(recall_bot_id=str(bot_id)).first()
    if not meeting:
        return None
    if meeting.bot_status != status_code:
        meeting.bot_status = str(status_code)[:30]
        db.session.commit()
        logger.info("recall_bot_status_updated", meeting_id=meeting.id,
                    bot_id=bot_id, status=status_code)
    return meeting


def pull_transcript_for_bot(bot_id):
    """Fetch the finished Recall transcript and store it on the meeting tied to this
    bot. Idempotent — skips if already pulled. Returns the Meeting (or None).

    Runs synchronously from the transcript.done webhook; transcripts are small enough
    that the extra HTTP hops stay well under Recall's webhook timeout.
    """
    from app.brain.meetings import recall  # local import keeps module load order simple
    meeting = Meeting.query.filter_by(recall_bot_id=str(bot_id)).first()
    if not meeting or meeting.transcript:
        return meeting
    try:
        text = recall.fetch_transcript_text(bot_id)
    except recall.RecallError as e:
        logger.warning("transcript_pull_failed", bot_id=bot_id, error=str(e))
        return meeting
    if text:
        meeting.transcript = text
        meeting.bot_status = "done"
        db.session.commit()
        logger.info("transcript_pulled", meeting_id=meeting.id, chars=len(text))
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
    was_accepted = item.status == "accepted"

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
    # On a fresh assignment (first accept with an owner), ping the assignee so the
    # to-do surfaces in their notification bell.
    if action == "accept" and item.owner_user_id and not was_accepted:
        _notify_assignee(item)
    return item


def _notify_assignee(item):
    """Notify the owner of a newly-assigned to-do so it surfaces in their bell.
    Fires even on self-assignment — an assigned to-do is meant to land in the bell as
    the owner's inbox, including when the reviewer assigns it to themselves."""
    due = f" (due {item.due_date.isoformat()})" if item.due_date else ""
    db.session.add(Notification(
        user_id=item.owner_user_id,
        type="checklist_assigned",
        message=f"New to-do: {item.title[:160]}{due}",
        checklist_item_id=item.id,
    ))
    db.session.commit()
    logger.info("checklist_assigned", item_id=item.id, owner_id=item.owner_user_id)


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
