"""
@milehigh-header
schema_version: 1
purpose: CRUD routes for the admin Kanban bug/feature tracker, including drag-drop reordering and @mention notifications.
exports:
  list_board_items: GET /board/items with filtering and comment counts (avoids N+1)
  create_board_item: POST /board/items
  add_board_activity: POST /board/items/<id>/activity — parses @mentions, creates Notification records
  reorder_board_items: PATCH /board/items/reorder — bulk position update for drag-drop
  ...and 4 more
imports_from: [app/brain, app/auth/utils, app/models, app/logging_config, flask, sqlalchemy]
imported_by: [app/brain/__init__.py]
invariants:
  - All routes require @admin_required; do not add public routes to this blueprint.
  - Routes are registered on brain_bp (imported from app/brain), not a local blueprint.
  - Comment @mention parsing uses re.findall(r'@(\w+)') and matches against User.first_name — must stay in sync with frontend MentionInput.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Board routes — CRUD for feature/bug tracking items and their activity threads.
All routes are admin-only.
"""
from flask import request, jsonify
from sqlalchemy import func
from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
from app.brain.mentions import parse_mentions, resolve_mentioned_users
from app.models import db, BoardItem, BoardActivity, User, Notification
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route('/board/mentionable-users', methods=['GET'])
@admin_required
def list_mentionable_users():
    """List active users for @mention autocomplete."""
    users = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    return jsonify({'users': [
        {
            'id': u.id,
            'first_name': u.first_name or u.username,
            'last_name': u.last_name or '',
        }
        for u in users
    ]})


@brain_bp.route('/board/items', methods=['GET'])
@admin_required
def list_board_items():
    """List board items with optional filters."""
    status = request.args.get('status')
    category = request.args.get('category')
    priority = request.args.get('priority')
    search = request.args.get('search')

    # Subquery to count comments per item (avoids N+1)
    comment_counts = (
        db.session.query(
            BoardActivity.item_id,
            func.count(BoardActivity.id).label('comment_count')
        )
        .filter(BoardActivity.type == 'comment')
        .group_by(BoardActivity.item_id)
        .subquery()
    )

    query = (
        db.session.query(BoardItem, comment_counts.c.comment_count)
        .outerjoin(comment_counts, BoardItem.id == comment_counts.c.item_id)
    )

    if status:
        query = query.filter(BoardItem.status == status)
    if category:
        query = query.filter(BoardItem.category == category)
    if priority:
        query = query.filter(BoardItem.priority == priority)
    if search:
        term = f'%{search}%'
        query = query.filter(
            db.or_(
                BoardItem.title.ilike(term),
                BoardItem.body.ilike(term),
            )
        )

    rows = query.order_by(
        BoardItem.position.asc().nullsfirst(),
        BoardItem.created_at.desc()
    ).all()
    return jsonify({'items': [item.to_dict(activity_count=count or 0) for item, count in rows]})


@brain_bp.route('/board/items/reorder', methods=['PATCH'])
@admin_required
def reorder_board_items():
    """Bulk-update card positions within a single status column."""
    data = request.get_json()
    status_value = data.get('status')
    ordered_ids = data.get('ordered_ids', [])

    valid_statuses = {'open', 'in_progress', 'deployed', 'closed'}
    if status_value not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    if not isinstance(ordered_ids, list) or not ordered_ids:
        return jsonify({'error': 'ordered_ids must be a non-empty list'}), 400

    # Verify all IDs belong to this column (prevents cross-column injection)
    existing_ids = {
        row.id for row in
        db.session.query(BoardItem.id)
        .filter(BoardItem.status == status_value, BoardItem.id.in_(ordered_ids))
        .all()
    }
    if len(existing_ids) != len(ordered_ids):
        return jsonify({'error': 'One or more IDs not found in this column'}), 400

    id_to_pos = {item_id: idx for idx, item_id in enumerate(ordered_ids)}
    for item in db.session.query(BoardItem).filter(BoardItem.id.in_(ordered_ids)).all():
        item.position = id_to_pos[item.id]

    db.session.commit()
    logger.info(f"Reordered {len(ordered_ids)} items in column '{status_value}'")
    return jsonify({'ok': True, 'updated': len(ordered_ids)})


@brain_bp.route('/board/items', methods=['POST'])
@admin_required
def create_board_item():
    """Create a new board item."""
    data = request.get_json()
    user = get_current_user()

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'error': 'Title is required'}), 400

    category = data.get('category', '').strip()
    if not category:
        return jsonify({'error': 'Category is required'}), 400

    item = BoardItem(
        title=title,
        body=data.get('body', '').strip() or None,
        category=category,
        status=data.get('status', 'open'),
        priority=data.get('priority', 'normal'),
        author_id=user.id,
        author_name=user.first_name or user.username,
    )
    db.session.add(item)
    db.session.commit()

    logger.info(f"Board item #{item.id} created by {user.username}: {title}")
    return jsonify(item.to_dict(include_activity=True)), 201


@brain_bp.route('/board/items/<int:item_id>', methods=['GET'])
@admin_required
def get_board_item(item_id):
    """Get a single board item with its activity thread."""
    item = BoardItem.query.get_or_404(item_id)
    return jsonify(item.to_dict(include_activity=True))


@brain_bp.route('/board/items/<int:item_id>', methods=['PATCH'])
@admin_required
def update_board_item(item_id):
    """Update a board item. Auto-logs status changes to activity."""
    item = BoardItem.query.get_or_404(item_id)
    data = request.get_json()
    user = get_current_user()

    # Track status change before applying
    old_status = item.status
    new_status = data.get('status')

    if 'title' in data:
        item.title = data['title'].strip()
    if 'body' in data:
        item.body = data['body'].strip() or None
    if 'category' in data:
        item.category = data['category'].strip()
    if 'priority' in data:
        item.priority = data['priority']
    if new_status and new_status != old_status:
        item.status = new_status
        activity = BoardActivity(
            item_id=item.id,
            type='status_change',
            body=f'Changed status from {old_status} to {new_status}',
            old_value=old_status,
            new_value=new_status,
            author_id=user.id,
            author_name=user.first_name or user.username,
        )
        db.session.add(activity)

    db.session.commit()
    return jsonify(item.to_dict(include_activity=True))


@brain_bp.route('/board/items/<int:item_id>', methods=['DELETE'])
@admin_required
def delete_board_item(item_id):
    """Delete a board item and all its activity."""
    item = BoardItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    logger.info(f"Board item #{item_id} deleted by {get_current_user().username}")
    return jsonify({'ok': True})


@brain_bp.route('/board/items/<int:item_id>/activity', methods=['POST'])
@admin_required
def add_board_activity(item_id):
    """Add a comment to a board item."""
    item = BoardItem.query.get_or_404(item_id)
    data = request.get_json()
    user = get_current_user()

    body = data.get('body', '').strip()
    if not body:
        return jsonify({'error': 'Comment body is required'}), 400

    activity = BoardActivity(
        item_id=item_id,
        type='comment',
        body=body,
        author_id=user.id,
        author_name=user.first_name or user.username,
    )
    db.session.add(activity)
    db.session.commit()

    # Parse @FirstName mentions and create notifications
    mentioned_users = resolve_mentioned_users(parse_mentions(body))
    if mentioned_users:
        author_name = user.first_name or user.username
        for mu in mentioned_users:
            notif = Notification(
                user_id=mu.id,
                type='mention',
                message=f'{author_name} mentioned you',
                board_item_id=item.id,
                board_activity_id=activity.id,
            )
            db.session.add(notif)
        db.session.commit()

    return jsonify(activity.to_dict()), 201
