"""HTTP routes for native T&M ticket creation (registered on brain_bp).

POST /brain/tm-tickets                     create a draft ticket from form JSON (admin)
GET  /brain/tm-tickets?status=             list tickets
GET  /brain/tm-tickets/<id>                ticket detail + release candidates
PUT  /brain/tm-tickets/<id>                edit a draft ticket (admin)
POST /brain/tm-tickets/<id>/void           discard — kept as void, never deleted (admin)
GET  /brain/tm-tickets/release-candidates?job=   releases matching a job number (picker)
GET  /brain/tm-tickets/<id>/file           serve a parked legacy upload's original document

v1 is admin-only for writes (the foreman/PM/subcontractor role model comes with
the signature/approval phase). The legacy-paper upload/extract route is parked —
service.create_from_upload has no HTTP surface here.
"""
import io

from flask import request, jsonify, send_file

from app.brain import brain_bp
from app.auth.utils import login_required, admin_required, get_current_user
from app.brain.tm import service, storage
from app.logging_config import get_logger

logger = get_logger(__name__)


def _username():
    user = get_current_user()
    return user.username if user else None


@brain_bp.route("/tm-tickets", methods=["POST"])
@admin_required
def create_tm_ticket():
    body = request.get_json(silent=True) or {}
    ticket, error = service.create_ticket(body, _username())
    if error:
        return jsonify({"error": error}), 400
    return jsonify({
        "ticket": ticket.to_dict(),
        "release_candidates": service.release_candidates(ticket.job),
    }), 201


@brain_bp.route("/tm-tickets", methods=["GET"])
@login_required
def list_tm_tickets():
    status = request.args.get("status") or None
    return jsonify({"tickets": service.list_tickets(status=status)}), 200


@brain_bp.route("/tm-tickets/release-candidates", methods=["GET"])
@login_required
def tm_release_candidates():
    return jsonify({"candidates": service.release_candidates(request.args.get("job"))}), 200


@brain_bp.route("/tm-tickets/<int:ticket_id>", methods=["GET"])
@login_required
def get_tm_ticket(ticket_id):
    ticket = service.get_ticket(ticket_id)
    if ticket is None:
        return jsonify({"error": "Ticket not found"}), 404
    return jsonify({
        "ticket": ticket.to_dict(),
        "release_candidates": service.release_candidates(ticket.job),
    }), 200


@brain_bp.route("/tm-tickets/<int:ticket_id>", methods=["PUT"])
@admin_required
def update_tm_ticket(ticket_id):
    ticket = service.get_ticket(ticket_id)
    if ticket is None:
        return jsonify({"error": "Ticket not found"}), 404
    body = request.get_json(silent=True) or {}
    updated, error = service.update_ticket(ticket, body, _username())
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ticket": updated.to_dict()}), 200


@brain_bp.route("/tm-tickets/<int:ticket_id>/void", methods=["POST"])
@admin_required
def void_tm_ticket(ticket_id):
    ticket = service.get_ticket(ticket_id)
    if ticket is None:
        return jsonify({"error": "Ticket not found"}), 404
    return jsonify({"ticket": service.void_ticket(ticket, _username()).to_dict()}), 200


@brain_bp.route("/tm-tickets/<int:ticket_id>/file", methods=["GET"])
@login_required
def get_tm_ticket_file(ticket_id):
    """Serve a parked legacy upload's original document (native tickets have none)."""
    ticket = service.get_ticket(ticket_id)
    if ticket is None or not ticket.source_storage_key:
        return jsonify({"error": "Ticket not found"}), 404
    data = storage.read(ticket.source_storage_key)
    if not data:
        return jsonify({"error": "Document unavailable on this host"}), 404
    return send_file(
        io.BytesIO(data),
        mimetype=ticket.source_media_type or "application/octet-stream",
        download_name=ticket.source_filename or "tm-ticket",
    )
