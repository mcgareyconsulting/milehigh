"""REST endpoints for release photo attachments.

Endpoints (registered on brain_bp under the /brain prefix):
  POST   /releases/<release_id>/photos                       — upload an image
  GET    /releases/<release_id>/photos                       — list photos (newest first)
  GET    /releases/<release_id>/photos/<photo_id>/file       — stream the image bytes
  PATCH  /releases/<release_id>/photos/<photo_id>            — edit a photo's note
  DELETE /releases/<release_id>/photos/<photo_id>            — soft delete

Any logged-in user may add, view, annotate, or remove photos (unlike drawings,
which are drafter/admin only).
"""

from flask import jsonify, request, send_file

from app.brain import brain_bp
from app.auth.utils import login_required, get_current_user
from app.models import Releases, ReleasePhoto, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

from app.brain.job_log.features.photos.command import UploadPhotoCommand
from app.brain.job_log.features.photos.payloads import is_probably_image, sniff_image_mime
from app.brain.job_log.features.photos.storage import absolute_path

logger = get_logger(__name__)


@brain_bp.route('/releases/<int:release_id>/photos', methods=['POST'])
@login_required
def upload_release_photo(release_id):
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    file = request.files.get('file')
    if not file:
        return jsonify({'error': "Missing 'file' part"}), 400

    filename = file.filename or ''
    mimetype = (file.mimetype or '').lower()
    file_bytes = file.read()

    if not is_probably_image(file_bytes, mimetype, filename):
        return jsonify({'error': 'File must be an image'}), 400

    # Prefer a sniffed mime, fall back to the declared one (covers HEIC etc.).
    resolved_mime = sniff_image_mime(file_bytes) or (mimetype if mimetype.startswith('image/') else 'image/jpeg')

    note = (request.form.get('note') or '').strip() or None
    user = get_current_user()

    try:
        command = UploadPhotoCommand(
            release_id=release_id,
            file_bytes=file_bytes,
            filename=filename or None,
            mime_type=resolved_mime,
            uploaded_by_user_id=user.id,
            note=note,
        )
        photo = command.execute()
    except ValueError as exc:
        message = str(exc)
        status = 404 if 'not found' in message.lower() else 409
        return jsonify({'error': message}), status

    return jsonify(photo.to_dict()), 201


@brain_bp.route('/releases/<int:release_id>/photos', methods=['GET'])
@login_required
def list_release_photos(release_id):
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    photos = (ReleasePhoto.query
              .filter(ReleasePhoto.release_id == release_id,
                      ReleasePhoto.is_deleted.is_(False))
              .order_by(ReleasePhoto.uploaded_at.desc(), ReleasePhoto.id.desc())
              .all())

    return jsonify({
        'release_id': release_id,
        'photos': [p.to_dict() for p in photos],
    })


@brain_bp.route(
    '/releases/<int:release_id>/photos/<int:photo_id>/file',
    methods=['GET'],
)
@login_required
def get_release_photo_file(release_id, photo_id):
    photo = db.session.get(ReleasePhoto, photo_id)
    if not photo or photo.release_id != release_id or photo.is_deleted:
        return jsonify({'error': 'Photo not found'}), 404

    path = absolute_path(photo.storage_key)
    if not path.exists():
        logger.error(
            "Photo file missing on disk",
            extra={'release_id': release_id, 'photo_id': photo_id, 'storage_key': photo.storage_key},
        )
        return jsonify({'error': 'File missing on disk'}), 410

    return send_file(
        str(path),
        mimetype=photo.mime_type or 'image/jpeg',
        as_attachment=False,
        conditional=True,
    )


@brain_bp.route(
    '/releases/<int:release_id>/photos/<int:photo_id>',
    methods=['PATCH'],
)
@login_required
def update_release_photo(release_id, photo_id):
    photo = db.session.get(ReleasePhoto, photo_id)
    if not photo or photo.release_id != release_id or photo.is_deleted:
        return jsonify({'error': 'Photo not found'}), 404

    data = request.get_json(silent=True) or {}
    if 'note' not in data:
        return jsonify({'error': "Missing 'note'"}), 400

    note = data.get('note')
    photo.note = (note or '').strip() or None
    db.session.commit()

    return jsonify(photo.to_dict())


@brain_bp.route(
    '/releases/<int:release_id>/photos/<int:photo_id>',
    methods=['DELETE'],
)
@login_required
def delete_release_photo(release_id, photo_id):
    photo = db.session.get(ReleasePhoto, photo_id)
    if not photo or photo.release_id != release_id:
        return jsonify({'error': 'Photo not found'}), 404
    if photo.is_deleted:
        return jsonify({'status': 'already_deleted'}), 200

    release = db.session.get(Releases, release_id)
    user = get_current_user()

    photo.is_deleted = True
    JobEventService.create_and_close(
        job=release.job,
        release=release.release,
        action='delete_photo',
        source=f"Brain:{user.username}" if user else "Brain",
        payload={'photo_id': photo.id, 'soft': True},
    )
    db.session.commit()

    return jsonify({'status': 'deleted', 'photo_id': photo_id})
