"""BB (Banana Boy) read-only chat routes. Registered on brain_bp.

Access is gated by the per-user `is_bb_chat` flag (admins always have access), so the
phase-1 rollout can be widened from the admin UI without a redeploy. The chat is strictly
read-only — it answers questions by running SELECT queries and never mutates data.

Endpoints:
  POST   /brain/bb-chat                          send a message -> assistant answer + metrics
  GET    /brain/bb-chat/conversations            list my conversations
  GET    /brain/bb-chat/conversations/<id>       one conversation with its messages
  GET    /brain/bb-chat/admin/users              (admin) users + their is_bb_chat flag
  POST   /brain/bb-chat/admin/users/<id>/access  (admin) grant/revoke bb-chat access
"""
from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import admin_required, bb_chat_required, get_current_user
from app.models import db, User
from app.brain.bb_chat import service
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route('/bb-chat', methods=['POST'])
@bb_chat_required
def bb_chat_send():
    """Send a message. Body: {message, conversation_id?}. Returns the turn + metrics."""
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    conversation_id = data.get('conversation_id')
    if not message:
        return jsonify({'error': 'message is required'}), 400
    try:
        result = service.send_message(user.id, conversation_id, message)
        return jsonify(result), 200
    except PermissionError:
        return jsonify({'error': 'conversation not found'}), 404
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error('bb_chat_send_failed', user_id=user.id, error=str(exc),
                     error_type=type(exc).__name__, exc_info=True)
        return jsonify({'error': 'BB chat is temporarily unavailable.'}), 502


@brain_bp.route('/bb-chat/conversations', methods=['GET'])
@bb_chat_required
def bb_chat_conversations():
    """List the current user's conversations (metadata only)."""
    user = get_current_user()
    return jsonify({'conversations': service.list_conversations(user.id)}), 200


@brain_bp.route('/bb-chat/conversations/<int:conversation_id>', methods=['GET'])
@bb_chat_required
def bb_chat_conversation(conversation_id):
    """One conversation with its full message history (owner only)."""
    user = get_current_user()
    convo = service.get_conversation(user.id, conversation_id)
    if convo is None:
        return jsonify({'error': 'conversation not found'}), 404
    return jsonify(convo.to_dict(with_messages=True)), 200


# --- Admin: grant / revoke access (the "flip the flag" UI) ---------------------------

@brain_bp.route('/bb-chat/admin/users', methods=['GET'])
@admin_required
def bb_chat_admin_users():
    """All users with their BB-chat access flag, for the admin toggle panel."""
    users = User.query.order_by(User.username).all()
    return jsonify({'users': [
        {
            'id': u.id,
            'username': u.username,
            'name': ((u.first_name or '') + ' ' + (u.last_name or '')).strip() or u.username,
            'is_admin': bool(u.is_admin),
            'is_bb_chat': bool(getattr(u, 'is_bb_chat', False)),
        }
        for u in users
    ]}), 200


@brain_bp.route('/bb-chat/admin/users/<int:user_id>/access', methods=['POST'])
@admin_required
def bb_chat_admin_set_access(user_id):
    """Grant or revoke BB-chat access for a user. Body: {is_bb_chat: bool}."""
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({'error': 'user not found'}), 404
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('is_bb_chat'))
    target.is_bb_chat = enabled
    db.session.commit()
    actor = get_current_user()
    logger.info('bb_chat_access_changed', user_id=target.id,
                username=target.username, enabled=enabled,
                actor_id=actor.id if actor else None)
    return jsonify({'id': target.id, 'is_bb_chat': enabled}), 200
