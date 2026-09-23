"""
@milehigh-header
schema_version: 1
purpose: HTTP endpoint for the next-week installation schedule, registered on brain_bp at /brain/install-schedule.
exports:
  GET /brain/install-schedule/next-week?days=N — grouped-by-crew schedule envelope (read-only)
  GET /brain/install-schedule/by-day?days=N&past_days=N&installer=X&stage=S&month=YYYY-MM — day-row
    envelope for the vertical calendar (read-only); month= switches to one calendar month
imports_from: [flask, app.brain, app.auth.utils, app.route_utils, app.brain.install_schedule.service]
imported_by: [app/brain/__init__.py]
invariants:
  - login_required (any authenticated user; it's a production-meeting artifact, not admin-only).
  - Read-only; safe to poll. ``days``/``past_days`` clamped to 1..31 and 0..31.
  - Both endpoints serve the same cards from the same builders; they differ only in how the
    cards are grouped, so the two views can never disagree about a release.
"""
import re

from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import login_required
from app.route_utils import handle_errors
from app.logging_config import get_logger

from .service import build_day_schedule, build_month_schedule, build_next_week_schedule

logger = get_logger(__name__)


def _int_arg(name, default, lo, hi):
    """Read a clamped int query arg; a junk value falls back to the default rather
    than 400-ing, since every caller here is a dashboard poll."""
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, min(value, hi))


@brain_bp.route("/install-schedule/next-week", methods=["GET"])
@login_required
@handle_errors("load install schedule")
def install_schedule_next_week():
    return jsonify(build_next_week_schedule(days=_int_arg("days", 7, 1, 31)))


@brain_bp.route("/install-schedule/by-day", methods=["GET"])
@login_required
@handle_errors("load day schedule")
def install_schedule_by_day():
    """Day-row envelope backing the vertical calendar (the phone-shaped timeline)."""
    installer = (request.args.get("installer") or "").strip() or None
    stage = (request.args.get("stage") or "").strip() or None
    month = (request.args.get("month") or "").strip()
    if month:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            return jsonify({"error": "month must be YYYY-MM"}), 400
        year, mon = (int(p) for p in month.split("-", 1))
        return jsonify(build_month_schedule(year, mon, installer=installer, stage=stage))
    return jsonify(build_day_schedule(
        days=_int_arg("days", 14, 1, 31),
        past_days=_int_arg("past_days", 14, 0, 31),
        installer=installer,
        stage=stage,
    ))
