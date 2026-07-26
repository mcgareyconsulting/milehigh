"""
@milehigh-header
schema_version: 1
purpose: Admin-only HTTP endpoints for the Subs installer-invoice-paid page.
exports:
  GET  /brain/subs/releases
  PATCH /brain/subs/releases/<job>/<release>/installer-invoice-paid
imports_from: [flask, app.brain, app.auth.utils, app.route_utils, app.brain.subs.service]
imported_by: [app/brain/__init__.py]
invariants:
  - Both routes require admin.
  - installer_invoice_paid is not Releases.invoiced (customer billing).
"""
from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import admin_required
from app.route_utils import handle_errors
from app.logging_config import get_logger

from . import service

logger = get_logger(__name__)


def _parse_paid_arg(raw):
    """Parse ?paid=true|false into bool or None (omit / invalid → None = all)."""
    if raw is None or raw == "":
        return None
    lowered = str(raw).strip().lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    return None


@brain_bp.route("/subs/releases", methods=["GET"])
@admin_required
@handle_errors("list subs releases")
def list_subs_releases():
    """List active releases with an installer, sorted by installer / job / release.

    Query params:
        paid: true|false (optional) — filter by installer_invoice_paid
        installer: exact team name (optional)
    """
    paid = _parse_paid_arg(request.args.get("paid"))
    installer = request.args.get("installer") or None
    if installer is not None:
        installer = installer.strip() or None

    payload = service.list_subs_releases(paid=paid, installer=installer)
    return jsonify(payload), 200


@brain_bp.route(
    "/subs/releases/<int:job>/<release>/installer-invoice-paid",
    methods=["PATCH"],
)
@admin_required
@handle_errors("update installer invoice paid")
def update_installer_invoice_paid(job, release):
    """Toggle installer_invoice_paid for a release.

    Request body: { "installer_invoice_paid": true|false }
    """
    body = request.get_json(silent=True) or {}
    if "installer_invoice_paid" not in body:
        return jsonify({"error": "installer_invoice_paid is required"}), 400

    raw = body.get("installer_invoice_paid")
    if not isinstance(raw, bool):
        # Accept common string forms from form-like clients.
        if isinstance(raw, str) and raw.strip().lower() in ("true", "1", "yes"):
            raw = True
        elif isinstance(raw, str) and raw.strip().lower() in ("false", "0", "no"):
            raw = False
        else:
            return jsonify({"error": "installer_invoice_paid must be a boolean"}), 400

    try:
        result = service.set_installer_invoice_paid(job, release, raw)
    except ValueError:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(result), 200
