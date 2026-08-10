"""
@milehigh-header
schema_version: 1
purpose: Admin-only HTTP endpoints for the Subs installer-invoice page.
exports:
  GET   /brain/subs/releases
  PATCH /brain/subs/releases/<job>/<release>/installer-invoice-paid
  PATCH /brain/subs/releases/<job>/<release>/installer-invoice-progress
  PATCH /brain/subs/releases/<job>/<release>/installer-invoice-numbers
imports_from: [flask, app.brain, app.auth.utils, app.route_utils, app.brain.subs.service]
imported_by: [app/brain/__init__.py]
invariants:
  - All routes require admin.
  - installer_invoice_* fields are not Releases.invoiced (customer billing).
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


def _parse_bool_body(raw):
    """Accept bool or common string forms; return (ok, value)."""
    if isinstance(raw, bool):
        return True, raw
    if isinstance(raw, str) and raw.strip().lower() in ("true", "1", "yes"):
        return True, True
    if isinstance(raw, str) and raw.strip().lower() in ("false", "0", "no"):
        return True, False
    return False, None


@brain_bp.route("/subs/releases", methods=["GET"])
@admin_required
@handle_errors("list subs releases")
def list_subs_releases():
    """List Invoice Paid releases (live assigned + archived until invoiced complete).

    Query params:
        paid: true|false (optional) — filter by installer_invoice_paid
        installer: exact team name (optional)
        q: free-text search (optional)
    """
    paid = _parse_paid_arg(request.args.get("paid"))
    installer = request.args.get("installer") or None
    if installer is not None:
        installer = installer.strip() or None
    q = request.args.get("q") or None
    if q is not None:
        q = q.strip() or None

    payload = service.list_subs_releases(paid=paid, installer=installer, q=q)
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

    ok, raw = _parse_bool_body(body.get("installer_invoice_paid"))
    if not ok:
        return jsonify({"error": "installer_invoice_paid must be a boolean"}), 400

    try:
        result = service.set_installer_invoice_paid(job, release, raw)
    except ValueError:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(result), 200


@brain_bp.route(
    "/subs/releases/<int:job>/<release>/installer-invoice-progress",
    methods=["PATCH"],
)
@admin_required
@handle_errors("update installer invoice progress")
def update_installer_invoice_progress(job, release):
    """Set installer_invoice_progress (0–100 integer, or null/empty to clear).

    Request body: { "installer_invoice_progress": 0..100 | null }
    """
    body = request.get_json(silent=True) or {}
    if "installer_invoice_progress" not in body:
        return jsonify({"error": "installer_invoice_progress is required"}), 400

    try:
        result = service.set_installer_invoice_progress(
            job, release, body.get("installer_invoice_progress")
        )
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("invalid_progress:"):
            return jsonify({"error": msg.split(":", 1)[1]}), 400
        return jsonify({"error": "Job not found"}), 404

    return jsonify(result), 200


@brain_bp.route(
    "/subs/releases/<int:job>/<release>/installer-invoice-numbers",
    methods=["PATCH"],
)
@admin_required
@handle_errors("update installer invoice numbers")
def update_installer_invoice_numbers(job, release):
    """Set installer_invoice_numbers (multi-line string, or empty/null to clear).

    Request body: { "installer_invoice_numbers": "..." }
    """
    body = request.get_json(silent=True) or {}
    if "installer_invoice_numbers" not in body:
        return jsonify({"error": "installer_invoice_numbers is required"}), 400

    try:
        result = service.set_installer_invoice_numbers(
            job, release, body.get("installer_invoice_numbers")
        )
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("invalid_numbers:"):
            return jsonify({"error": msg.split(":", 1)[1]}), 400
        return jsonify({"error": "Job not found"}), 404

    return jsonify(result), 200
