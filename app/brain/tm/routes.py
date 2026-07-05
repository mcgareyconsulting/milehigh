"""HTTP routes for T&M ticket ingestion (registered on brain_bp).

POST /brain/tm-tickets                     upload a document → extract → pending ticket (admin)
GET  /brain/tm-tickets?status=             list tickets
GET  /brain/tm-tickets/<id>                ticket detail + release candidates
GET  /brain/tm-tickets/<id>/file           serve the original uploaded document
GET  /brain/tm-tickets/release-candidates?job=   releases matching a job number (picker)
POST /brain/tm-tickets/<id>/confirm        apply reviewed fields, confirm (admin)
POST /brain/tm-tickets/<id>/reject         deny — kept as rejected, never deleted (admin)

v1 is admin-only for writes (the foreman/PM/subcontractor role model comes with
the mobile-entry phase).
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
def upload_tm_ticket():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "file is required"}), 400

    media_type = (file.mimetype or "").split(";")[0].strip().lower()
    if media_type not in storage.MEDIA_TYPE_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type '{media_type}'. "
                     f"Accepted: {', '.join(sorted(storage.MEDIA_TYPE_EXTENSIONS))}"
        }), 400

    data = file.read()
    if not data:
        return jsonify({"error": "file is empty"}), 400
    if len(data) > service.MAX_UPLOAD_BYTES:
        return jsonify({"error": "file exceeds 20 MB limit"}), 400

    ticket = service.create_from_upload(data, media_type, file.filename, _username())
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


@brain_bp.route("/tm-tickets/<int:ticket_id>/file", methods=["GET"])
@login_required
def get_tm_ticket_file(ticket_id):
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


@brain_bp.route("/tm-tickets/<int:ticket_id>/confirm", methods=["POST"])
@admin_required
def confirm_tm_ticket(ticket_id):
    ticket = service.get_ticket(ticket_id)
    if ticket is None:
        return jsonify({"error": "Ticket not found"}), 404
    body = request.get_json(silent=True) or {}
    updated, error = service.confirm(ticket, body, _username())
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ticket": updated.to_dict()}), 200


@brain_bp.route("/tm-tickets/<int:ticket_id>/reject", methods=["POST"])
@admin_required
def reject_tm_ticket(ticket_id):
    ticket = service.get_ticket(ticket_id)
    if ticket is None:
        return jsonify({"error": "Ticket not found"}), 404
    return jsonify({"ticket": service.reject(ticket, _username()).to_dict()}), 200
