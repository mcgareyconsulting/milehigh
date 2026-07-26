"""HTTP routes for a subcontractor's own view of assigned T&M tickets
(registered on brain_bp). All routes require an active Subcontractor session
(subcontractor_login_required) and check assignment before touching a ticket
— an unassigned-but-real ticket id 404s, same as a nonexistent one, so
existence is never leaked.

GET  /brain/subcontractor/tm-tickets                    list assigned tickets
GET  /brain/subcontractor/tm-tickets/<id>                one ticket (must be assigned)
PUT  /brain/subcontractor/tm-tickets/<id>                edit while draft (delegates to service.update_ticket)
POST /brain/subcontractor/tm-tickets/<id>/submit         draft -> submitted (delegates to service.submit_ticket)
GET  /brain/subcontractor/tm-tickets/<id>/attachments    view-only list (no upload route here — see plan notes)
GET  /brain/subcontractor/tm-tickets/<id>/attachments/<attachment_id>/file   stream the file bytes
"""
from flask import request, jsonify, send_file

from app.brain import brain_bp
from app.subcontractor_auth.utils import subcontractor_login_required, get_current_subcontractor
from app.models import TMTicket, TMTicketAttachment, TMTicketSubcontractor, db
from app.brain.tm import service
from app.brain.tm.photos.storage import absolute_path
from app.logging_config import get_logger

logger = get_logger(__name__)


def _assigned_ticket_or_none(ticket_id: int, subcontractor_id: int) -> TMTicket | None:
    """A ticket only exists (from this subcontractor's point of view) if
    there's an assignment row — don't leak whether the id itself is real."""
    assignment = TMTicketSubcontractor.query.filter_by(
        tm_ticket_id=ticket_id, subcontractor_id=subcontractor_id).first()
    if not assignment:
        return None
    return db.session.get(TMTicket, ticket_id)


def _actor(sub) -> str:
    return f"subcontractor:{sub.id}:{sub.email}"


@brain_bp.route('/subcontractor/tm-tickets', methods=['GET'])
@subcontractor_login_required
def list_assigned_tickets():
    sub = get_current_subcontractor()
    tickets = (
        TMTicket.query
        .join(TMTicketSubcontractor, TMTicketSubcontractor.tm_ticket_id == TMTicket.id)
        .filter(TMTicketSubcontractor.subcontractor_id == sub.id)
        .order_by(TMTicket.created_at.desc(), TMTicket.id.desc())
        .all()
    )
    return jsonify({'tickets': [t.to_dict() for t in tickets]}), 200


@brain_bp.route('/subcontractor/tm-tickets/<int:ticket_id>', methods=['GET'])
@subcontractor_login_required
def get_assigned_ticket(ticket_id):
    sub = get_current_subcontractor()
    ticket = _assigned_ticket_or_none(ticket_id, sub.id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404
    return jsonify({'ticket': ticket.to_dict()}), 200


@brain_bp.route('/subcontractor/tm-tickets/<int:ticket_id>', methods=['PUT'])
@subcontractor_login_required
def update_assigned_ticket(ticket_id):
    sub = get_current_subcontractor()
    ticket = _assigned_ticket_or_none(ticket_id, sub.id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

    body = request.get_json(silent=True) or {}
    updated, error = service.update_ticket(ticket, body, _actor(sub))
    if error:
        return jsonify({'error': error}), 400
    return jsonify({'ticket': updated.to_dict()}), 200


@brain_bp.route('/subcontractor/tm-tickets/<int:ticket_id>/submit', methods=['POST'])
@subcontractor_login_required
def submit_assigned_ticket(ticket_id):
    sub = get_current_subcontractor()
    ticket = _assigned_ticket_or_none(ticket_id, sub.id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

    submitted, error = service.submit_ticket(ticket, _actor(sub))
    if error:
        return jsonify({'error': error}), 400
    return jsonify({'ticket': submitted.to_dict()}), 200


@brain_bp.route('/subcontractor/tm-tickets/<int:ticket_id>/attachments', methods=['GET'])
@subcontractor_login_required
def list_assigned_ticket_attachments(ticket_id):
    sub = get_current_subcontractor()
    ticket = _assigned_ticket_or_none(ticket_id, sub.id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

    attachments = (
        TMTicketAttachment.query
        .filter(TMTicketAttachment.tm_ticket_id == ticket_id, TMTicketAttachment.is_deleted.is_(False))
        .order_by(TMTicketAttachment.uploaded_at.desc(), TMTicketAttachment.id.desc())
        .all()
    )
    return jsonify({'attachments': [a.to_dict() for a in attachments]}), 200


@brain_bp.route('/subcontractor/tm-tickets/<int:ticket_id>/attachments/<int:attachment_id>/file', methods=['GET'])
@subcontractor_login_required
def get_assigned_ticket_attachment_file(ticket_id, attachment_id):
    sub = get_current_subcontractor()
    ticket = _assigned_ticket_or_none(ticket_id, sub.id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

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
