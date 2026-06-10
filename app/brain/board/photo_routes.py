"""REST endpoints for board item photo attachments.

Endpoints (registered on brain_bp under the /brain prefix):
  POST   /board/items/<item_id>/photos                      — upload an image
  GET    /board/items/<item_id>/photos                      — list photos (newest first)
  GET    /board/items/<item_id>/photos/<photo_id>/file      — stream the image bytes
  DELETE /board/items/<item_id>/photos/<photo_id>           — soft delete

Photos carry no per-photo caption (context lives in the card body). All routes
are admin-only, matching the rest of the board blueprint.
"""

from flask import jsonify, request, send_file

from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
from app.models import BoardItem, BoardItemPhoto, db
from app.logging_config import get_logger

from app.brain.board.photos.command import UploadBoardPhotoCommand
from app.brain.board.photos.storage import absolute_path
# Image sniffing/validation is generic — reuse the release photo helpers.
from app.brain.job_log.features.photos.payloads import is_probably_image, sniff_image_mime

logger = get_logger(__name__)


@brain_bp.route('/board/items/<int:item_id>/photos', methods=['POST'])
@admin_required
def upload_board_photo(item_id):
    item = db.session.get(BoardItem, item_id)
    if not item:
        return jsonify({'error': 'Board item not found'}), 404

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

    user = get_current_user()

    try:
        command = UploadBoardPhotoCommand(
            board_item_id=item_id,
            file_bytes=file_bytes,
            filename=filename or None,
            mime_type=resolved_mime,
            uploaded_by_user_id=user.id,
        )
        photo = command.execute()
    except ValueError as exc:
        message = str(exc)
        status = 404 if 'not found' in message.lower() else 409
        return jsonify({'error': message}), status

    return jsonify(photo.to_dict()), 201


@brain_bp.route('/board/items/<int:item_id>/photos', methods=['GET'])
@admin_required
def list_board_photos(item_id):
    item = db.session.get(BoardItem, item_id)
    if not item:
        return jsonify({'error': 'Board item not found'}), 404

    photos = (BoardItemPhoto.query
              .filter(BoardItemPhoto.board_item_id == item_id,
                      BoardItemPhoto.is_deleted.is_(False))
              .order_by(BoardItemPhoto.uploaded_at.desc(), BoardItemPhoto.id.desc())
              .all())

    return jsonify({
        'board_item_id': item_id,
        'photos': [p.to_dict() for p in photos],
    })


@brain_bp.route(
    '/board/items/<int:item_id>/photos/<int:photo_id>/file',
    methods=['GET'],
)
@admin_required
def get_board_photo_file(item_id, photo_id):
    photo = db.session.get(BoardItemPhoto, photo_id)
    if not photo or photo.board_item_id != item_id or photo.is_deleted:
        return jsonify({'error': 'Photo not found'}), 404

    path = absolute_path(photo.storage_key)
    if not path.exists():
        logger.error(
            "Board photo file missing on disk",
            extra={'board_item_id': item_id, 'photo_id': photo_id, 'storage_key': photo.storage_key},
        )
        return jsonify({'error': 'File missing on disk'}), 410

    return send_file(
        str(path),
        mimetype=photo.mime_type or 'image/jpeg',
        as_attachment=False,
        conditional=True,
    )


@brain_bp.route(
    '/board/items/<int:item_id>/photos/<int:photo_id>',
    methods=['DELETE'],
)
@admin_required
def delete_board_photo(item_id, photo_id):
    photo = db.session.get(BoardItemPhoto, photo_id)
    if not photo or photo.board_item_id != item_id:
        return jsonify({'error': 'Photo not found'}), 404
    if photo.is_deleted:
        return jsonify({'status': 'already_deleted'}), 200

    photo.is_deleted = True
    db.session.commit()

    return jsonify({'status': 'deleted', 'photo_id': photo_id})
