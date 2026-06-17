"""
@milehigh-header
schema_version: 1
purpose: To-do list endpoints over assigned checklist items. An admin sees every assigned
         to-do (filterable by owner/status); a non-admin sees only their own. The owner or
         an admin can mark a to-do done / reopen it.
exports:
  list_todos: GET /todos — assigned to-dos (scoped by role, filterable).
  update_todo: PATCH /todos/<id> — owner/admin marks a to-do done or accepted (reopen).
  release_checklist: GET /releases/<id>/checklist — read-only to-dos + meeting notes for one release.
imports_from: [flask, app.brain, app.auth.utils, app.models, app.logging_config]
imported_by: [app/brain/__init__.py]
invariants:
  - login_required on all routes; non-admins are hard-scoped to owner_user_id == themselves.
  - A "to-do" is an accepted/done checklist item with an owner (proposed/rejected excluded).
  - release_checklist is GET-only and never mutates — it backs the read-only timeline detail modal.
"""
from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import login_required, get_current_user
from app.models import db, ChecklistItem, Meeting, Releases
from app.logging_config import get_logger

logger = get_logger(__name__)

TODO_STATUSES = ("accepted", "done")


@brain_bp.route('/todos', methods=['GET'])
@login_required
def list_todos():
    """Assigned to-dos. Admin: all (optional ?owner=<id>); non-admin: own only.
    ?status = open (default) | done | all."""
    user = get_current_user()
    status = (request.args.get('status') or 'open').lower()

    q = ChecklistItem.query.filter(
        ChecklistItem.status.in_(TODO_STATUSES),
        ChecklistItem.owner_user_id.isnot(None),
    )
    if not user.is_admin:
        q = q.filter(ChecklistItem.owner_user_id == user.id)
    else:
        owner = request.args.get('owner')
        if owner and owner.isdigit():
            q = q.filter(ChecklistItem.owner_user_id == int(owner))

    if status == 'open':
        q = q.filter(ChecklistItem.status == 'accepted')
    elif status == 'done':
        q = q.filter(ChecklistItem.status == 'done')
    # 'all' → both accepted and done

    # Soonest due first; undated last.
    rows = q.order_by(
        ChecklistItem.due_date.is_(None),
        ChecklistItem.due_date.asc(),
        ChecklistItem.id.desc(),
    ).all()

    mids = {it.meeting_id for it in rows}
    titles = dict(
        Meeting.query.with_entities(Meeting.id, Meeting.title)
        .filter(Meeting.id.in_(mids)).all()
    ) if mids else {}

    todos = []
    for it in rows:
        d = it.to_dict()
        d['meeting_title'] = titles.get(it.meeting_id)
        todos.append(d)
    return jsonify({'todos': todos, 'is_admin': bool(user.is_admin)})


@brain_bp.route('/todos/<int:item_id>', methods=['PATCH'])
@login_required
def update_todo(item_id):
    """Mark a to-do done or reopen it. Allowed for the owner or an admin."""
    user = get_current_user()
    item = db.session.get(ChecklistItem, item_id)
    if not item:
        return jsonify({'error': 'not found'}), 404
    if not (user.is_admin or item.owner_user_id == user.id):
        return jsonify({'error': 'forbidden'}), 403

    new_status = ((request.get_json(silent=True) or {}).get('status') or '').lower()
    if new_status not in ('done', 'accepted'):
        return jsonify({'error': 'status must be done or accepted'}), 400

    item.status = new_status
    db.session.commit()
    logger.info("todo_status_changed", item_id=item.id, status=new_status, by=user.id)
    return jsonify(item.to_dict())


@brain_bp.route('/releases/<int:release_id>/checklist', methods=['GET'])
@login_required
def release_checklist(release_id):
    """Read-only active to-dos + the meeting notes they came from, for one release.

    Backs the timeline detail modal. Unlike /todos this is keyed on the release (not
    the viewer), so any logged-in user can see a release's to-dos. GET-only; the
    timeline never mutates.
    """
    if not db.session.get(Releases, release_id):
        return jsonify({'error': 'release not found'}), 404

    rows = (
        ChecklistItem.query.filter(
            ChecklistItem.release_id == release_id,
            ChecklistItem.status.in_(TODO_STATUSES),
            ChecklistItem.owner_user_id.isnot(None),
        )
        .order_by(
            ChecklistItem.due_date.is_(None),
            ChecklistItem.due_date.asc(),
            ChecklistItem.id.desc(),
        )
        .all()
    )

    mids = {it.meeting_id for it in rows}
    meetings = (
        Meeting.query.filter(Meeting.id.in_(mids))
        .order_by(Meeting.occurred_at.is_(None), Meeting.occurred_at.desc())
        .all()
        if mids else []
    )
    titles = {m.id: m.title for m in meetings}

    todos = []
    for it in rows:
        d = it.to_dict()
        d['meeting_title'] = titles.get(it.meeting_id)
        todos.append(d)

    # Lean meeting projection — title + when + summary for read-only context. We
    # deliberately skip the full transcript that Meeting.to_dict(include_items=True) dumps.
    meeting_notes = [
        {
            'id': m.id,
            'title': m.title,
            'meeting_type': m.meeting_type,
            'occurred_at': m.occurred_at.isoformat() if m.occurred_at else None,
            'summary': m.summary,
        }
        for m in meetings
    ]

    return jsonify({'release_id': release_id, 'todos': todos, 'meetings': meeting_notes})
