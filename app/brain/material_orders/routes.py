"""HTTP routes for supplier material orders (registered on brain_bp).

GET  /brain/material-orders?job=&release=   list orders for a release (modal)
POST /brain/material-orders/<id>/received    mark received / un-receive (drafter+)
POST /brain/material-orders/ingest           backfill orders from lake emails (admin)
"""
from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import login_required, drafter_or_admin_required, admin_required
from app.logging_config import get_logger
from app.brain.material_orders import service

logger = get_logger(__name__)


@brain_bp.route("/material-orders", methods=["GET"])
@login_required
def list_material_orders():
    job = request.args.get("job")
    release = request.args.get("release")
    if job is None:
        return jsonify({"error": "job is required"}), 400
    try:
        orders = service.list_for_release(job, release)
    except (TypeError, ValueError):
        return jsonify({"error": "job must be an integer"}), 400
    return jsonify({"orders": orders}), 200


@brain_bp.route("/material-orders/<int:order_id>/received", methods=["POST"])
@drafter_or_admin_required
def set_material_order_received(order_id):
    body = request.get_json(silent=True) or {}
    received = bool(body.get("received", True))
    result = service.mark_received(order_id, received=received)
    if result is None:
        return jsonify({"error": "Material order not found"}), 404
    return jsonify({"order": result}), 200


@brain_bp.route("/material-orders/ingest", methods=["POST"])
@admin_required
def ingest_material_orders():
    """Backfill MaterialOrders from already-landed lake email records."""
    body = request.get_json(silent=True) or {}
    limit = body.get("limit", 200)
    created = service.ingest_unprocessed(limit=limit)
    return jsonify({"status": "ok", "created": created}), 200
