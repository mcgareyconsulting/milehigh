"""Meeting → checklist service: create+extract, review (yes/no/edit), notify owners.

Kept as plain service functions (the routes delegate here), mirroring the brain
feature-command split without the event/outbox machinery — checklist items are not
release-scoped and have no async external push.
"""
import re
from concurrent.futures import ThreadPoolExecutor
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

# The web dyno runs no APScheduler (that's the IS_RENDER_SCHEDULER process), so the
# multi-minute extraction can't block the request — gunicorn's worker timeout would
# SIGKILL the worker mid-call and the request 500s with no logs. Offload to an
# in-process pool, mirroring how Trello sync hands work to a ThreadPoolExecutor.
_EXTRACT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="meeting-extract")
# A run whose started_at is older than this is presumed dead (worker recycled mid-run)
# and may be relaunched; until then a repeat Generate click is a no-op. Must outlast the
# longest LEGITIMATE run — all-Opus on a big production meeting (extract + owner match +
# summary, each with multi-minute timeouts) can pass 10 minutes; a premature relaunch
# runs CONCURRENTLY with the live run and double-inserts items.
EXTRACT_STALE_AFTER = timedelta(minutes=20)


def start_extraction(app, meeting_id, *, regenerate=False):
    """Queue background checklist extraction for a meeting. The caller must have already
    flipped extract_status to 'extracting' and committed; this only runs the work
    off-thread and returns immediately."""
    _EXTRACT_POOL.submit(_run_extraction_job, app, meeting_id, regenerate)


def _run_extraction_job(app, meeting_id, regenerate):
    """Background body of an extraction: mine the transcript, then stamp the meeting
    done/failed. Always logs and never lets the worker thread die silently — this is the
    error path that was invisible when extraction ran (and timed out) inside the request."""
    with app.app_context():
        try:
            meeting = db.session.get(Meeting, meeting_id)
            if not meeting:
                logger.warning("extract_job_meeting_missing", meeting_id=meeting_id)
                return
            extract_into_meeting(meeting, regenerate=regenerate)
            meeting.extract_status = "done"
            meeting.extract_error = None
            db.session.commit()
            logger.info("extract_job_done", meeting_id=meeting_id)
        except Exception as e:  # noqa: BLE001 — record + log, never crash the worker
            logger.error("extract_job_failed", meeting_id=meeting_id,
                         error=str(e), exc_info=True)
            db.session.rollback()
            failed = db.session.get(Meeting, meeting_id)
            if failed:
                failed.extract_status = "failed"
                failed.extract_error = str(e)[:1000]
                db.session.commit()
        finally:
            db.session.remove()


def get_reviewer():
    """The user who reviews post-meeting checklists (MVP: Bill, by config)."""
    return User.query.filter_by(username=cfg.CHECKLIST_REVIEWER_USERNAME).first()


def _resolve_owner_id(owner_name):
    """Resolve an extracted owner_name to an ACTIVE user id, or None.

    Org gate: a name that isn't a current employee (out-of-org, a garbled transcript
    token like 'RO/Ror', or ambiguous) yields None — the to-do is left unassigned for the
    reviewer rather than guessed. Delegates to the same resolver the job-inference layer
    uses (owner_match.resolve_name_to_user), so first / last / full-name handling and the
    org gate stay consistent across both owner sources."""
    from app.brain.meetings.owner_match import resolve_name_to_user
    return resolve_name_to_user(owner_name)


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
    # Two context streams, two outputs:
    #   - EXTRACTION context (agenda + light job state + learned guidance) grounds the to-dos.
    #   - The events that landed DURING the meeting ground the summary — and are stored on
    #     context_snapshot since that activity is what drifts and is worth recording.
    from app.brain.meetings import context as meeting_context
    ctx = meeting_context.assemble_extraction_context(meeting)
    events_block = meeting_context.build_runtime_events(meeting)
    meeting.context_snapshot = events_block or None
    result = extract(meeting.transcript or "", people=people, context=ctx["combined"])
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

    # Second output: the meeting summary, grounded by the during-meeting events and
    # judged against the agenda (plan vs. what happened — never restated). Same
    # generate step so one click produces both outputs; never raises.
    from app.brain.meetings import summary as meeting_summary
    sresult = meeting_summary.summarize(meeting.transcript or "", events_block,
                                        agenda=(meeting.agenda_text or ""))
    meeting.summary = sresult["summary"] or None
    summary_usage = sresult["usage"]

    # Blend the three LLM passes (extract + owner-match + summary) into one cost meter.
    tags = [usage["model"]]
    in_tok = usage["input_tokens"] or 0
    out_tok = usage["output_tokens"] or 0
    cost = usage["cost_usd"] or 0
    for label, extra in (("match", match_usage), ("summary", summary_usage)):
        if extra.get("cost_usd"):
            in_tok += extra.get("input_tokens") or 0
            out_tok += extra.get("output_tokens") or 0
            cost += extra.get("cost_usd") or 0
            tags.append(label)
    meeting.extract_model = (" +".join(tags))[:40]  # extract_model is VARCHAR(40)
    meeting.extract_input_tokens = in_tok
    meeting.extract_output_tokens = out_tok
    meeting.extract_cost_usd = round(cost, 6)
    db.session.commit()

    if notify:
        _notify_reviewer(meeting, created)
    logger.info("meeting_extracted", meeting_id=meeting.id, items=created)
    return created


def create_meeting_with_extraction(*, title, meeting_type, transcript,
                                   project_number=None, occurred_at=None,
                                   agenda_text=None, created_by_id=None):
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
        agenda_text=(agenda_text or None),
        created_by=created_by_id,
    )
    db.session.add(meeting)
    db.session.commit()  # persist before the (slow, external) extraction
    extract_into_meeting(meeting)
    return meeting


def create_manual_meeting(*, title, meeting_type, transcript, agenda_text=None,
                          created_by_id=None):
    """Create a meeting from a pasted transcript WITHOUT extracting — the checklist is
    generated on demand via the 'Generate to-do list' button (so the transcript goes
    straight to the LLM only when the reviewer asks). Returns the Meeting."""
    meeting = Meeting(
        title=(title or "Pasted meeting")[:255],
        meeting_type=meeting_type or "other",
        source="manual",
        transcript=transcript,
        agenda_text=(agenda_text or None),
        occurred_at=datetime.utcnow(),
        created_by=created_by_id,
    )
    db.session.add(meeting)
    db.session.commit()
    logger.info("manual_meeting_created", meeting_id=meeting.id,
                chars=len(transcript or ""))
    return meeting


def create_recall_meeting(*, meeting_url, bot_id, title=None, meeting_type=None,
                          agenda_text=None, created_by_id=None):
    """Persist a meeting whose transcript will come from a Recall bot.

    Immediate-send MVP: the bot joins now, so occurred_at is stamped now. No
    transcript/extraction yet — that arrives via the pull step. bot_status starts at
    'joining' and is kept fresh by the recall-webhook receiver. agenda_text is the
    pre-meeting context the user dropped in when dispatching the bot.
    """
    meeting = Meeting(
        title=(title or "Recall meeting")[:255],
        meeting_type=meeting_type or "other",
        source="recall",
        meeting_url=(meeting_url or "")[:1000] or None,
        recall_bot_id=bot_id,
        bot_status="joining",
        agenda_text=(agenda_text or None),
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
        # Stamp meeting end on a terminal status (bounds the summary's event window) if
        # the transcript pull hasn't already done so.
        if str(status_code) in ("done", "failed") and not meeting.ended_at:
            meeting.ended_at = datetime.utcnow()
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
        # The bot has left the call — stamp the meeting end so the summary's
        # "events during meeting" window [occurred_at, ended_at] is bounded.
        if not meeting.ended_at:
            meeting.ended_at = datetime.utcnow()
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
    was_proposed = item.status == "proposed"

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
    # When this action retired the LAST un-reviewed item, the checklist is fully worked —
    # synthesize learnings from the yes/no/edit outcomes. Fires exactly once (guarded on
    # this item having just left 'proposed').
    if action and was_proposed:
        _maybe_trigger_learning(item.meeting_id)
    return item


def _maybe_trigger_learning(meeting_id):
    """Kick off background learnings synthesis once no proposed items remain for the
    meeting. No-op outside an app context (e.g. a bare unit test) — safe to call anywhere."""
    remaining = ChecklistItem.query.filter_by(
        meeting_id=meeting_id, status="proposed").count()
    if remaining:
        return
    try:
        from flask import current_app
        from app.brain.meetings import learn
        learn.start_learning(current_app._get_current_object(), meeting_id)
        logger.info("learning_triggered", meeting_id=meeting_id)
    except Exception as e:  # noqa: BLE001 — never let learning kickoff break a review
        logger.info("learning_trigger_skipped", meeting_id=meeting_id, error=str(e))


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
