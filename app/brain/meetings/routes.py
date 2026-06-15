"""Meeting ingestion (stubbed) + checklist review routes. Registered on brain_bp.

Admin-only, matching the board's posture. Endpoints:
  POST   /brain/meetings                     ingest a transcript -> proposed checklist
  GET    /brain/meetings                      recent meetings
  GET    /brain/meetings/<id>                 meeting + its checklist items
  PATCH  /brain/meetings/<id>                 edit pre-meeting context (agenda_text)
  POST   /brain/meetings/<id>/learn           (re)synthesize learnings from the review
  GET    /brain/meetings/checklist/pending    proposed items awaiting review
  GET    /brain/meetings/assignable-users     active users for the owner picker
  PATCH  /brain/checklist-items/<id>          accept / reject / done / edit (owner+date)
  POST   /brain/checklist-items/scan-due      manual deadline-notification scan
"""
from datetime import datetime

from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
from app.models import db, Meeting, ChecklistItem, User
from app.brain.meetings import service, recall
from app.brain.meetings.recall import RecallError
from app.logging_config import get_logger

logger = get_logger(__name__)

# Recall webhook events we surface as the meeting's bot_status. Anything not listed
# (bot.breakout_room_*, bot.recording_permission_allowed, transcript.deleted, …) is
# acknowledged with 200 but ignored, so the status stays meaningful.
_BOT_STATUS = {
    'joining_call': 'joining',
    'in_waiting_room': 'in_waiting_room',
    'in_call_not_recording': 'in_call_not_recording',
    'in_call_recording': 'in_call_recording',
    'recording_permission_denied': 'recording_denied',
    'call_ended': 'call_ended',
    'done': 'done',
    'fatal': 'fatal',
}
_TRANSCRIPT_STATUS = {'processing': 'transcribing', 'done': 'done', 'failed': 'failed'}


@brain_bp.route('/meetings/assignable-users', methods=['GET'])
@admin_required
def list_assignable_users():
    """Active users for the owner dropdown in the review UI."""
    users = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    return jsonify({'users': [
        {'id': u.id, 'first_name': u.first_name or u.username, 'last_name': u.last_name or ''}
        for u in users
    ]})


@brain_bp.route('/meetings/bots', methods=['POST'])
@admin_required
def send_meeting_bot():
    """Dispatch a Recall notetaker bot to a meeting URL (Teams / Google Meet / Zoom)
    and persist a meeting card. Immediate-send: the bot joins now.

    Transcript pull + extraction are separate later steps; here we just dispatch and
    record the meeting so it shows on the tab with a live bot_status. Returns the
    meeting dict.
    """
    data = request.get_json(silent=True) or {}
    meeting_url = (data.get('meeting_url') or '').strip()
    if not meeting_url:
        return jsonify({'error': 'meeting_url is required'}), 400
    try:
        bot_id = recall.dispatch_bot(
            meeting_url, bot_name=(data.get('bot_name') or 'BB'),
        )
    except RecallError as e:
        logger.warning('send_meeting_bot_failed', error=str(e))
        return jsonify({'error': str(e)}), 502

    user = get_current_user()
    meeting = service.create_recall_meeting(
        meeting_url=meeting_url,
        bot_id=bot_id,
        title=(data.get('title') or data.get('name')),
        meeting_type=data.get('meeting_type'),
        agenda_text=(data.get('agenda_text') or '').strip() or None,
        created_by_id=user.id if user else None,
    )
    return jsonify(meeting.to_dict()), 201


@brain_bp.route('/meetings', methods=['POST'])
@admin_required
def create_meeting():
    """Ingest a transcript (stubbed ingestion) and surface a proposed checklist."""
    data = request.get_json(silent=True) or {}
    transcript = (data.get('transcript') or '').strip()
    if not transcript:
        return jsonify({'error': 'transcript is required'}), 400

    occurred_at = None
    if data.get('occurred_at'):
        try:
            occurred_at = datetime.fromisoformat(str(data['occurred_at'])[:19])
        except ValueError:
            occurred_at = None

    user = get_current_user()
    meeting = service.create_meeting_with_extraction(
        title=data.get('title'),
        meeting_type=data.get('meeting_type'),
        transcript=transcript,
        project_number=data.get('project_number'),
        occurred_at=occurred_at,
        agenda_text=(data.get('agenda_text') or '').strip() or None,
        created_by_id=user.id if user else None,
    )
    return jsonify(meeting.to_dict(include_items=True)), 201


@brain_bp.route('/meetings', methods=['GET'])
@admin_required
def list_meetings():
    rows = Meeting.query.order_by(Meeting.created_at.desc()).limit(100).all()
    return jsonify({'meetings': [m.to_dict() for m in rows]})


@brain_bp.route('/meetings/manual', methods=['POST'])
@admin_required
def add_manual_meeting():
    """Create a meeting from a pasted transcript (no auto-extraction). The reviewer
    then runs the extractor via the 'Generate to-do list' button. Returns the meeting."""
    data = request.get_json(silent=True) or {}
    transcript = (data.get('transcript') or '').strip()
    if not transcript:
        return jsonify({'error': 'transcript is required'}), 400
    user = get_current_user()
    m = service.create_manual_meeting(
        title=data.get('title'),
        meeting_type=data.get('meeting_type'),
        transcript=transcript,
        agenda_text=(data.get('agenda_text') or '').strip() or None,
        created_by_id=user.id if user else None,
    )
    return jsonify(m.to_dict(include_items=True)), 201


@brain_bp.route('/meetings/<int:meeting_id>/generate-checklist', methods=['POST'])
@admin_required
def generate_checklist(meeting_id):
    """On-demand: mine the meeting's transcript into a proposed checklist (the
    'Generate to-do list' button).

    The extraction makes multi-minute LLM calls, so it runs in a background thread and
    this returns 202 immediately with extract_status='extracting'; the UI polls
    GET /meetings/<id> until it leaves that state. Running it inline used to exceed
    gunicorn's worker timeout and 500 with no logs."""
    from flask import current_app

    m = db.session.get(Meeting, meeting_id)
    if not m:
        return jsonify({'error': 'not found'}), 404
    if not (m.transcript or '').strip():
        return jsonify({'error': 'no transcript to generate from yet'}), 400

    # Idempotent: if a run is already in flight (and not stale), report it rather than
    # launching a duplicate.
    in_flight = (
        m.extract_status == 'extracting' and m.extract_started_at
        and datetime.utcnow() - m.extract_started_at < service.EXTRACT_STALE_AFTER
    )
    if in_flight:
        return jsonify(m.to_dict(include_items=True)), 202

    data = request.get_json(silent=True) or {}
    m.extract_status = 'extracting'
    m.extract_error = None
    m.extract_started_at = datetime.utcnow()
    db.session.commit()
    service.start_extraction(
        current_app._get_current_object(), m.id,
        regenerate=bool(data.get('regenerate')),
    )
    return jsonify(m.to_dict(include_items=True)), 202


@brain_bp.route('/meetings/<int:meeting_id>', methods=['GET'])
@admin_required
def get_meeting(meeting_id):
    m = db.session.get(Meeting, meeting_id)
    if not m:
        return jsonify({'error': 'not found'}), 404
    return jsonify(m.to_dict(include_items=True))


@brain_bp.route('/meetings/<int:meeting_id>', methods=['PATCH'])
@admin_required
def update_meeting(meeting_id):
    """Edit pre-meeting context after creation — e.g. add agenda/notes to an
    already-dispatched bot meeting before generating its checklist."""
    m = db.session.get(Meeting, meeting_id)
    if not m:
        return jsonify({'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}
    if 'agenda_text' in data:
        m.agenda_text = (data.get('agenda_text') or '').strip() or None
        db.session.commit()
    return jsonify(m.to_dict(include_items=True))


@brain_bp.route('/meetings/<int:meeting_id>/learn', methods=['POST'])
@admin_required
def generate_learnings(meeting_id):
    """Manually (re)synthesize learnings for a meeting from its reviewed checklist.
    Runs in the background like extraction; the UI re-fetches the meeting to see the
    new learning. Also runs automatically once the last proposed item is reviewed."""
    from flask import current_app
    from app.brain.meetings import learn

    m = db.session.get(Meeting, meeting_id)
    if not m:
        return jsonify({'error': 'not found'}), 404
    learn.start_learning(current_app._get_current_object(), m.id)
    return jsonify({'ok': True, 'meeting_id': m.id}), 202


@brain_bp.route('/meetings/checklist/pending', methods=['GET'])
@admin_required
def pending_checklist():
    """Proposed (un-reviewed) items awaiting the reviewer, newest meeting first."""
    rows = (ChecklistItem.query
            .filter(ChecklistItem.status == 'proposed')
            .order_by(ChecklistItem.meeting_id.desc(), ChecklistItem.id)
            .all())
    return jsonify({'items': [i.to_dict() for i in rows]})


@brain_bp.route('/checklist-items/<int:item_id>', methods=['PATCH'])
@admin_required
def review_checklist_item(item_id):
    """Curate an item: action in {accept, reject, done} and/or edit `fields`
    (owner_user_id, due_date, title, detail, item_type, gc_facing, links)."""
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action and action not in ('accept', 'reject', 'done'):
        return jsonify({'error': 'invalid action'}), 400
    item = service.review_item(
        item_id, action=action, fields=data.get('fields') or {},
        reviewer=get_current_user(),
    )
    if not item:
        return jsonify({'error': 'not found'}), 404
    return jsonify(item.to_dict())


@brain_bp.route('/checklist-items/scan-due', methods=['POST'])
@admin_required
def scan_due_items():
    """Manually run the deadline-notification scan (also runs on a schedule)."""
    return jsonify({'notified': service.notify_due_items()})


@brain_bp.route('/meetings/recall-webhook', methods=['HEAD', 'POST'])
def recall_webhook():
    """Receive Recall.ai webhook events. PUBLIC (no auth) — Recall posts server-to-server.

    Short-term posture is PULL, so this is intentionally thin: it acknowledges the
    event (so Recall's test-event button and real deliveries get a 200 through the
    ngrok tunnel) and logs it. The functional hook — mapping `data.bot.id` back to a
    Meeting via recall_bot_id and auto-running the pull on `transcript.done` — lands
    once steps 2/3 add the column + dispatch flow. Until then we never 4xx, so a test
    event never looks like a wiring failure.
    """
    if request.method == 'HEAD':
        return '', 200

    payload = request.get_json(silent=True) or {}
    event = payload.get('event') or 'unknown'
    data = payload.get('data') or {}
    bot = data.get('bot') or {}
    bot_id = bot.get('id') or data.get('bot_id')
    logger.info('recall_webhook_received', recall_event=event, bot_id=bot_id)

    # Map only the meaningful lifecycle events to a status — everything else Recall
    # sends (breakout rooms, recording_permission_allowed, transcript.deleted) is
    # acknowledged but ignored so the meeting status stays meaningful.
    status_code = None
    if event == 'bot.status_change':
        status_code = _BOT_STATUS.get((data.get('status') or {}).get('code'))
    elif event.startswith('bot.'):
        status_code = _BOT_STATUS.get(event.split('bot.', 1)[1])
    elif event.startswith('transcript.'):
        status_code = _TRANSCRIPT_STATUS.get(event.split('transcript.', 1)[1])

    if bot_id and status_code:
        service.update_bot_status(bot_id, status_code)
    # Pull the finished transcript onto the meeting once it's ready.
    if event == 'transcript.done' and bot_id:
        service.pull_transcript_for_bot(bot_id)

    return jsonify({'ok': True, 'event': event}), 200
