"""
@milehigh-header
schema_version: 1
purpose: Provide REST endpoints for the in-app @mention notification system used by the board feature.
exports:
  list_notifications: GET /notifications — recent notifications with unread count (?types, ?limit, ?owner).
  unread_notification_count: GET /notifications/unread-count — lightweight polling endpoint for the notification bell.
  mark_notification_read: PATCH /notifications/<id>/read — marks a single notification as read.
  mark_all_notifications_read: POST /notifications/read-all — marks unread notifications read (?types narrows).
imports_from: [flask, app.brain, app.auth.utils, sqlalchemy.orm, app.models, app.logging_config]
imported_by: [app/brain/__init__.py]
invariants:
  - All routes require @login_required; users can only access their own notifications.
  - Notification records are created by board comment logic (app/brain/board/routes.py), not here.
  - ?types is a whitelist filter only — it never widens scope past the selected recipient.
  - ?owner is honored for admins only; a non-admin is always pinned to their own rows, and
    an absent ?owner means "me" so the bell's plain GET is unchanged.
  - Read-state writes (PATCH read, POST read-all) stay self-only regardless of ?owner —
    an admin can look at another user's mentions but never dismiss them.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Notification routes — in-app notifications for @mentions.
"""
from flask import request, jsonify
from app.brain import brain_bp
from app.auth.utils import login_required, get_current_user
from sqlalchemy.orm import joinedload
from app.models import db, Notification, User, DrawingVersionComment
from app.logging_config import get_logger

logger = get_logger(__name__)


DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _display_name(user):
    """Best available human name for a User row."""
    if user is None:
        return None
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username


def _resolve_owner_scope(user, raw):
    """Resolve ?owner into a recipient filter.

    Returns (user_id_or_None, scoped_to_self). A non-admin is always pinned to
    their own rows — the parameter is ignored for them, never trusted. For an
    admin, 'all' widens to every recipient and a numeric id targets one person;
    anything else (including an absent param) means "just me", which keeps the
    notification bell's plain GET behaving exactly as it always has.
    """
    if not user.is_admin:
        return user.id, True
    owner = (raw or '').strip().lower()
    if owner == 'all':
        return None, False
    if owner.isdigit():
        target = int(owner)
        return target, target == user.id
    return user.id, True


@brain_bp.route('/notifications', methods=['GET'])
@login_required
def list_notifications():
    """List notifications for the current user.

    ?types=mention,dwl_mention narrows to specific notification types (the To-Dos
    mentions column asks for mentions only, so a burst of to-do notifications
    cannot push them past the row cap). ?limit caps the page (default 50).
    ?owner=<id>|all retargets the recipient — admins only; see _resolve_owner_scope.
    """
    user = get_current_user()
    owner_id, scoped_to_self = _resolve_owner_scope(user, request.args.get('owner'))

    q = Notification.query.options(
        joinedload(Notification.board_item),
        joinedload(Notification.board_activity),
        joinedload(Notification.submittal),
        # The drawing-comment payload reads through to the version + release,
        # so pull those in the same trip rather than N+1-ing per row.
        joinedload(Notification.drawing_version_comment)
        .joinedload(DrawingVersionComment.drawing_version),
        joinedload(Notification.drawing_version_comment)
        .joinedload(DrawingVersionComment.release),
    )
    if owner_id is not None:
        q = q.filter(Notification.user_id == owner_id)
    if not scoped_to_self:
        # Only an off-self view needs the recipient's name, so the bell's own
        # fetch never pays for the join.
        q = q.options(joinedload(Notification.user))

    types = [t.strip() for t in (request.args.get('types') or '').split(',') if t.strip()]
    if types:
        q = q.filter(Notification.type.in_(types))

    limit = request.args.get('limit', type=int) or DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    notifications = q.order_by(Notification.created_at.desc()).limit(limit).all()

    rows = []
    for n in notifications:
        d = n.to_dict()
        if not scoped_to_self:
            d['owner_name'] = _display_name(n.user)
        rows.append(d)

    unread_count = sum(1 for n in notifications if not n.is_read)
    return jsonify({
        'notifications': rows,
        'unread_count': unread_count,
        'is_admin': bool(user.is_admin),
        'scoped_to_self': scoped_to_self,
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
    """Mark all unread notifications as read for the current user.

    ?types=... narrows the sweep, so the To-Dos mentions column can clear its own
    unread without also dismissing to-do / review notifications. There is
    deliberately no ?owner here: an admin browsing someone else's mentions can
    read them, never mark them read on that person's behalf.
    """
    user = get_current_user()
    q = Notification.query.filter_by(user_id=user.id, is_read=False)
    types = [t.strip() for t in (request.args.get('types') or '').split(',') if t.strip()]
    if types:
        q = q.filter(Notification.type.in_(types))
    q.update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return jsonify({'ok': True})


@brain_bp.route('/mentionable-users', methods=['GET'])
@login_required
def list_mentionable_users_all():
    """List active users for @mention autocomplete (available to any logged-in user)."""
    users = User.query.filter_by(is_active=True).order_by(User.first_name).all()
    return jsonify({'users': [
        {
            'id': u.id,
            'first_name': u.first_name or u.username,
            'last_name': u.last_name or '',
        }
        for u in users
    ]})
