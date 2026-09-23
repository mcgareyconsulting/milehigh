"""
@milehigh-header
schema_version: 1
purpose: Subcontractor-facing release routes (T3 slice 1) — the crew-scoped read model
  behind the sub timeline.
exports: (none — routes register on brain_bp)
imports_from: [flask, app.brain, app.subcontractor_auth.utils, app.brain.sub_portal.service]
imported_by: [app/brain/__init__.py]
invariants:
  - @subcontractor_login_required only. An internal User session is NOT accepted here,
    matching the decorator's own rule — the two identity spaces never cross.
  - No route in this module serves the changelog. Subs get Activity (slice 4), and the
    changelog is blocked by never having a route that returns it, not by a hidden tab.

GET   /brain/subcontractor/releases                  crew-scoped releases, allowlist-serialized
GET   /brain/subcontractor/releases/<id>             one crew-scoped release (404 off-crew)
GET   /brain/subcontractor/installer-teams           the caller's own crew, as a list
GET   /brain/subcontractor/install-schedule/by-day   the phone Timeline envelope, crew pinned
GET   /brain/subcontractor/todos?status=             the sub's own to-dos
PATCH /brain/subcontractor/todos/<id>                done <-> accepted on their own to-do
GET   /brain/subcontractor/notifications             their mentions / to-do pings
GET   /brain/subcontractor/notifications/unread-count
PATCH /brain/subcontractor/notifications/<id>/read
POST  /brain/subcontractor/notifications/read-all
GET   /brain/subcontractor/releases/<id>/activity          Activity rows (SUB_ACTIVITY_ACTIONS)
POST  /brain/subcontractor/releases/<id>/notes             post a note (body: {notes})
GET   /brain/subcontractor/releases/<id>/attachments       drawings + photos, allowlisted
GET   /brain/subcontractor/releases/<id>/drawing/versions/<vid>/file
GET   /brain/subcontractor/releases/<id>/photos/<pid>/file
POST  /brain/subcontractor/releases/<id>/photos                multipart image (+ note)
PATCH /brain/subcontractor/releases/<id>/stage                  {stage} in SUB_STAGES
GET   /brain/subcontractor/releases/<id>/splices                the release family
"""
from flask import jsonify, request, send_file

from app.brain import brain_bp
from app.brain.job_log.features.pdf_markup.storage import absolute_path as drawing_path
from app.brain.job_log.features.photos.storage import absolute_path as photo_path
from app.brain.sub_portal.service import (
    SUB_STAGES,
    add_note_for_subcontractor,
    list_family_for_subcontractor,
    set_stage_for_subcontractor,
    upload_photo_for_subcontractor,
    build_day_schedule_for_subcontractor,
    get_release_for_subcontractor,
    list_activity_for_subcontractor,
    list_attachments_for_subcontractor,
    resolve_drawing_file_for_subcontractor,
    resolve_photo_file_for_subcontractor,
    list_notifications_for_subcontractor,
    list_releases_for_subcontractor,
    list_todos_for_subcontractor,
    mark_all_read_for_subcontractor,
    mark_notification_read_for_subcontractor,
    set_todo_status_for_subcontractor,
    unread_count_for_subcontractor,
)
from app.logging_config import get_logger
from app.subcontractor_auth.utils import get_current_subcontractor, subcontractor_login_required

logger = get_logger(__name__)


@brain_bp.route('/subcontractor/releases', methods=['GET'])
@subcontractor_login_required
def list_subcontractor_releases():
    """The releases assigned to this account's installer crew.

    Full load only. Cursor/incremental refresh (the `since` param the internal
    /brain/jobs feed carries) waits for the timeline in slice 3, so the shape of the
    polling contract is decided once, against a real consumer.
    """
    sub = get_current_subcontractor()
    releases = list_releases_for_subcontractor(sub)
    return jsonify({'releases': releases, 'installer_team': sub.installer_team}), 200


@brain_bp.route('/subcontractor/installer-teams', methods=['GET'])
@subcontractor_login_required
def list_subcontractor_installer_teams():
    """The caller's own crew, as a one-element list (empty if unscoped).

    A sub-scoped counterpart to /brain/installer-teams, which is @login_required and
    returns the FULL roster. The timeline blocks its initial load on the teams fetch,
    so without this route a subcontractor session 401s and the page never finishes
    loading — and serving the internal route would name every other crew to them.
    """
    sub = get_current_subcontractor()
    crew = (sub.installer_team or '').strip()
    return jsonify({'installer_teams': [crew] if crew else []}), 200


def _int_arg(name, default, lo, hi):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, min(value, hi))


@brain_bp.route('/subcontractor/releases/<int:release_id>', methods=['GET'])
@subcontractor_login_required
def get_subcontractor_release(release_id):
    """One release on the caller's crew — the read-only detail sheet behind a card tap.
    Off-crew and unknown ids both 404, so the response never confirms an id exists."""
    payload = get_release_for_subcontractor(get_current_subcontractor(), release_id)
    if payload is None:
        return jsonify({'error': 'Release not found'}), 404
    return jsonify({'release': payload, 'stage_options': list(SUB_STAGES)}), 200


@brain_bp.route('/subcontractor/install-schedule/by-day', methods=['GET'])
@subcontractor_login_required
def subcontractor_day_schedule():
    """The phone Timeline. The crew is the session's, never a query param: a sub cannot
    ask for another crew's days by editing the URL."""
    sub = get_current_subcontractor()
    return jsonify(build_day_schedule_for_subcontractor(
        sub,
        days=_int_arg('days', 14, 1, 31),
        past_days=_int_arg('past_days', 14, 0, 31),
    )), 200


@brain_bp.route('/subcontractor/todos', methods=['GET'])
@subcontractor_login_required
def list_subcontractor_todos():
    status = (request.args.get('status') or 'open').lower()
    if status not in ('open', 'done', 'all'):
        status = 'open'
    return jsonify({'todos': list_todos_for_subcontractor(get_current_subcontractor(), status)}), 200


@brain_bp.route('/subcontractor/todos/<int:item_id>', methods=['PATCH'])
@subcontractor_login_required
def update_subcontractor_todo(item_id):
    new_status = ((request.get_json(silent=True) or {}).get('status') or '').lower()
    if new_status not in ('done', 'accepted'):
        return jsonify({'error': 'status must be done or accepted'}), 400
    payload = set_todo_status_for_subcontractor(get_current_subcontractor(), item_id, new_status)
    if payload is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(payload), 200


@brain_bp.route('/subcontractor/notifications', methods=['GET'])
@subcontractor_login_required
def list_subcontractor_notifications():
    sub = get_current_subcontractor()
    rows = list_notifications_for_subcontractor(sub, limit=request.args.get('limit', type=int) or 50)
    return jsonify({
        'notifications': rows,
        'unread_count': sum(1 for r in rows if not r['is_read']),
    }), 200


@brain_bp.route('/subcontractor/notifications/unread-count', methods=['GET'])
@subcontractor_login_required
def subcontractor_unread_count():
    return jsonify(unread_count_for_subcontractor(get_current_subcontractor())), 200


@brain_bp.route('/subcontractor/notifications/<int:notification_id>/read', methods=['PATCH'])
@subcontractor_login_required
def mark_subcontractor_notification_read(notification_id):
    payload = mark_notification_read_for_subcontractor(get_current_subcontractor(), notification_id)
    if payload is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(payload), 200


@brain_bp.route('/subcontractor/notifications/read-all', methods=['POST'])
@subcontractor_login_required
def mark_all_subcontractor_notifications_read():
    types = [t.strip() for t in (request.args.get('types') or '').split(',') if t.strip()]
    updated = mark_all_read_for_subcontractor(get_current_subcontractor(), types or None)
    return jsonify({'ok': True, 'updated': updated}), 200


@brain_bp.route('/subcontractor/releases/<int:release_id>/activity', methods=['GET'])
@subcontractor_login_required
def subcontractor_release_activity(release_id):
    rows = list_activity_for_subcontractor(
        get_current_subcontractor(), release_id, limit=request.args.get('limit', type=int) or 200)
    if rows is None:
        return jsonify({'error': 'Release not found'}), 404
    return jsonify({'events': rows}), 200


@brain_bp.route('/subcontractor/releases/<int:release_id>/notes', methods=['POST'])
@subcontractor_login_required
def subcontractor_post_note(release_id):
    body = request.get_json(silent=True) or {}
    try:
        result = add_note_for_subcontractor(get_current_subcontractor(), release_id, body.get('notes'))
    except ValueError as exc:
        if str(exc) == 'Event already exists':
            return jsonify({'error': 'That note was just posted'}), 400
        return jsonify({'error': str(exc)}), 400
    if result is None:
        return jsonify({'error': 'Release not found'}), 404
    event_id, notes = result
    return jsonify({'status': 'success', 'event_id': event_id, 'notes': notes}), 201


@brain_bp.route('/subcontractor/releases/<int:release_id>/attachments', methods=['GET'])
@subcontractor_login_required
def subcontractor_release_attachments(release_id):
    payload = list_attachments_for_subcontractor(get_current_subcontractor(), release_id)
    if payload is None:
        return jsonify({'error': 'Release not found'}), 404
    return jsonify(payload), 200


@brain_bp.route('/subcontractor/releases/<int:release_id>/drawing/versions/<int:version_id>/file', methods=['GET'])
@subcontractor_login_required
def subcontractor_drawing_file(release_id, version_id):
    version = resolve_drawing_file_for_subcontractor(get_current_subcontractor(), release_id, version_id)
    if version is None:
        return jsonify({'error': 'Not found'}), 404
    path = drawing_path(version.storage_key)
    if not path.exists():
        logger.error("drawing_file_missing", release_id=release_id, version_id=version_id, exc_info=True)
        return jsonify({'error': 'File missing on disk'}), 410
    return send_file(str(path), mimetype=version.mime_type or 'application/pdf',
                     as_attachment=False, conditional=True)


@brain_bp.route('/subcontractor/releases/<int:release_id>/photos/<int:photo_id>/file', methods=['GET'])
@subcontractor_login_required
def subcontractor_photo_file(release_id, photo_id):
    photo = resolve_photo_file_for_subcontractor(get_current_subcontractor(), release_id, photo_id)
    if photo is None:
        return jsonify({'error': 'Not found'}), 404
    path = photo_path(photo.storage_key)
    if not path.exists():
        logger.error("photo_file_missing", release_id=release_id, photo_id=photo_id, exc_info=True)
        return jsonify({'error': 'File missing on disk'}), 410
    return send_file(str(path), mimetype=photo.mime_type or 'image/jpeg',
                     as_attachment=False, conditional=True)


@brain_bp.route('/subcontractor/releases/<int:release_id>/photos', methods=['POST'])
@subcontractor_login_required
def subcontractor_upload_photo(release_id):
    file = request.files.get('file')
    if not file:
        return jsonify({'error': "Missing 'file' part"}), 400
    try:
        payload = upload_photo_for_subcontractor(
            get_current_subcontractor(), release_id, file.read(), file.filename or '',
            (file.mimetype or '').lower(), note=request.form.get('note'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if payload is None:
        return jsonify({'error': 'Release not found'}), 404
    return jsonify(payload), 201


@brain_bp.route('/subcontractor/releases/<int:release_id>/stage', methods=['PATCH'])
@subcontractor_login_required
def subcontractor_set_stage(release_id):
    from app.brain.job_log.features.stage.command import StagePhotoRequiredError
    stage = (request.get_json(silent=True) or {}).get('stage')
    try:
        result = set_stage_for_subcontractor(get_current_subcontractor(), release_id, stage)
    except StagePhotoRequiredError as exc:
        return jsonify({'error': str(exc), 'code': 'photo_required', 'stage': exc.stage}), 422
    except ValueError as exc:
        msg = str(exc)
        if 'already exists' in msg.lower():
            return jsonify({'error': 'That change was just made'}), 400
        return jsonify({'error': msg}), 400
    if result is None:
        return jsonify({'error': 'Release not found'}), 404
    return jsonify({'status': 'success', 'event_id': result.event_id, 'stage': result.stage}), 200


@brain_bp.route('/subcontractor/releases/<int:release_id>/splices', methods=['GET'])
@subcontractor_login_required
def subcontractor_release_splices(release_id):
    rows = list_family_for_subcontractor(get_current_subcontractor(), release_id)
    if rows is None:
        return jsonify({'error': 'Release not found'}), 404
    return jsonify({'family': rows}), 200
