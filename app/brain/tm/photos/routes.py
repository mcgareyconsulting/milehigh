"""REST endpoints for T&M ticket photo/video attachments.

Endpoints (registered on brain_bp under the /brain prefix):
  POST   /tm-tickets/<id>/attachments                 — upload a photo/video (draft-only)
  GET    /tm-tickets/<id>/attachments                 — list attachments (newest first)
  GET    /tm-tickets/<id>/attachments/<attachment_id>/file  — stream the file bytes
  DELETE /tm-tickets/<id>/attachments/<attachment_id> — soft delete (draft-only)

All routes are admin-only, matching the rest of the tm blueprint (v1 is
admin-only for writes; the foreman/PM/subcontractor role model comes with the
signature/approval phase).
"""
from flask import jsonify, request, send_file

from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
from app.models import TMTicket, TMTicketAttachment, db
from app.logging_config import get_logger

from app.brain.tm.photos.command import UploadTMTicketAttachmentCommand, delete_attachment
from app.brain.tm.photos.storage import absolute_path
from app.brain.tm.photos.payloads import is_probably_media, sniff_media_mime

logger = get_logger(__name__)


@brain_bp.route('/tm-tickets/<int:ticket_id>/attachments', methods=['POST'])
@admin_required
def upload_tm_ticket_attachment(ticket_id):
    ticket = db.session.get(TMTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

    file = request.files.get('file')
    if not file:
        return jsonify({'error': "Missing 'file' part"}), 400

    filename = file.filename or ''
    mimetype = (file.mimetype or '').lower()
    file_bytes = file.read()

    if not is_probably_media(file_bytes, mimetype, filename):
        return jsonify({'error': 'File must be a photo or video'}), 400

    resolved_mime = sniff_media_mime(file_bytes) or (
        mimetype if (mimetype.startswith('image/') or mimetype.startswith('video/')) else 'application/octet-stream'
    )

    user = get_current_user()

    try:
        command = UploadTMTicketAttachmentCommand(
            tm_ticket_id=ticket_id,
            file_bytes=file_bytes,
            filename=filename or None,
            mime_type=resolved_mime,
            uploaded_by_user_id=user.id,
        )
        attachment = command.execute()
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 400
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404

    return jsonify(attachment.to_dict()), 201


@brain_bp.route('/tm-tickets/<int:ticket_id>/attachments', methods=['GET'])
@admin_required
def list_tm_ticket_attachments(ticket_id):
    ticket = db.session.get(TMTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

    attachments = (TMTicketAttachment.query
                   .filter(TMTicketAttachment.tm_ticket_id == ticket_id,
                           TMTicketAttachment.is_deleted.is_(False))
                   .order_by(TMTicketAttachment.uploaded_at.desc(), TMTicketAttachment.id.desc())
                   .all())

    return jsonify({
        'tm_ticket_id': ticket_id,
        'attachments': [a.to_dict() for a in attachments],
    }), 200


@brain_bp.route('/tm-tickets/<int:ticket_id>/attachments/<int:attachment_id>/file', methods=['GET'])
@admin_required
def get_tm_ticket_attachment_file(ticket_id, attachment_id):
    attachment = db.session.get(TMTicketAttachment, attachment_id)
    if not attachment or attachment.tm_ticket_id != ticket_id or attachment.is_deleted:
        return jsonify({'error': 'Attachment not found'}), 404

    path = absolute_path(attachment.storage_key)
    if not path.exists():
        logger.error("tm_ticket_attachment_file_missing", tm_ticket_id=ticket_id,
                     attachment_id=attachment_id, exc_info=False)
        return jsonify({'error': 'File missing on disk'}), 410

    return send_file(
        str(path),
        mimetype=attachment.mime_type or 'application/octet-stream',
        as_attachment=False,
        conditional=True,
    )


@brain_bp.route('/tm-tickets/<int:ticket_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@admin_required
def delete_tm_ticket_attachment(ticket_id, attachment_id):
    attachment = db.session.get(TMTicketAttachment, attachment_id)
    if not attachment or attachment.tm_ticket_id != ticket_id:
        return jsonify({'error': 'Attachment not found'}), 404
    if attachment.is_deleted:
        return jsonify({'status': 'already_deleted'}), 200

    try:
        delete_attachment(attachment)
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'status': 'deleted', 'attachment_id': attachment_id}), 200
