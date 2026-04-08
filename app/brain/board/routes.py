"""
Board routes — CRUD for feature/bug tracking items and their activity threads.
All routes are admin-only.
"""
from flask import request, jsonify
from sqlalchemy import func
from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
import re
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

    rows = query.order_by(BoardItem.updated_at.desc()).all()
    return jsonify({'items': [item.to_dict(activity_count=count or 0) for item, count in rows]})


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
    mentions = re.findall(r'@(\w+)', body)
    if mentions:
        mentioned_users = User.query.filter(
            db.func.lower(User.first_name).in_([m.lower() for m in mentions]),
            User.is_active.is_(True),
            User.id != user.id,
        ).all()
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
        if mentioned_users:
            db.session.commit()

    return jsonify(activity.to_dict()), 201
