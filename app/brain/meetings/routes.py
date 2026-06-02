"""Meeting ingestion (stubbed) + checklist review routes. Registered on brain_bp.

Admin-only, matching the board's posture. Endpoints:
  POST   /brain/meetings                     ingest a transcript -> proposed checklist
  GET    /brain/meetings                      recent meetings
  GET    /brain/meetings/<id>                 meeting + its checklist items
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
from app.brain.meetings import service
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route('/meetings/assignable-users', methods=['GET'])
@admin_required
def list_assignable_users():
    """Active users for the owner dropdown in the review UI."""
    users = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    return jsonify({'users': [
        {'id': u.id, 'first_name': u.first_name or u.username, 'last_name': u.last_name or ''}
        for u in users
    ]})


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
        created_by_id=user.id if user else None,
    )
    return jsonify(meeting.to_dict(include_items=True)), 201


@brain_bp.route('/meetings', methods=['GET'])
@admin_required
def list_meetings():
    rows = Meeting.query.order_by(Meeting.created_at.desc()).limit(100).all()
    return jsonify({'meetings': [m.to_dict() for m in rows]})


@brain_bp.route('/meetings/<int:meeting_id>', methods=['GET'])
@admin_required
def get_meeting(meeting_id):
    m = db.session.get(Meeting, meeting_id)
    if not m:
        return jsonify({'error': 'not found'}), 404
    return jsonify(m.to_dict(include_items=True))


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
