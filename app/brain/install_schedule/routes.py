"""
@milehigh-header
schema_version: 1
purpose: HTTP endpoint for the next-week installation schedule, registered on brain_bp at /brain/install-schedule.
exports:
  GET /brain/install-schedule/next-week?days=N — grouped-by-crew schedule envelope (read-only)
imports_from: [flask, app.brain, app.auth.utils, app.route_utils, app.brain.install_schedule.service]
imported_by: [app/brain/__init__.py]
invariants:
  - login_required (any authenticated user; it's a production-meeting artifact, not admin-only).
  - Read-only; safe to poll. ``days`` clamped to 1..31.
"""
from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import login_required
from app.route_utils import handle_errors
from app.logging_config import get_logger

from .service import build_next_week_schedule

logger = get_logger(__name__)


@brain_bp.route("/install-schedule/next-week", methods=["GET"])
@login_required
@handle_errors("load install schedule")
def install_schedule_next_week():
    try:
        days = int(request.args.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, 31))
    return jsonify(build_next_week_schedule(days=days))
