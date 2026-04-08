"""
Notification routes — in-app notifications for @mentions.
"""
from flask import request, jsonify
from app.brain import brain_bp
from app.auth.utils import login_required, get_current_user
from sqlalchemy.orm import joinedload
from app.models import db, Notification
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route('/notifications', methods=['GET'])
@login_required
def list_notifications():
    """List notifications for the current user."""
    user = get_current_user()
    notifications = (Notification.query
                     .filter_by(user_id=user.id)
                     .options(joinedload(Notification.board_item))
                     .order_by(Notification.created_at.desc())
                     .limit(50)
                     .all())
    unread_count = sum(1 for n in notifications if not n.is_read)
    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count,
    })


@brain_bp.route('/notifications/unread-count', methods=['GET'])
@login_required
def unread_notification_count():
    """Lightweight unread count for polling."""
    user = get_current_user()
    count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify({'unread_count': count})


@brain_bp.route('/notifications/<int:notification_id>/read', methods=['PATCH'])
@login_required
def mark_notification_read(notification_id):
    """Mark a single notification as read."""
    user = get_current_user()
    notif = Notification.query.get_or_404(notification_id)
    if notif.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403
    notif.is_read = True
    db.session.commit()
    return jsonify(notif.to_dict())


@brain_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all unread notifications as read for the current user."""
    user = get_current_user()
    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True})
