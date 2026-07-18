"""System-usage metrics endpoints (admin-only), registered on ``brain_bp``.

The JSON contract is the primary deliverable — the admin dashboard and any agent
(BB01, scheduled digest) read the same responses. All routes accept
``?period=day|week|month`` (default ``week``) plus optional ``?start=&end=`` ISO
overrides. Every response shares a ``{period, start, end, generated_at, ...}``
envelope.
"""
from datetime import datetime

from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import admin_required
from app.route_utils import handle_errors
from app.logging_config import get_logger

from . import queries
from .timeframe import resolve_window

logger = get_logger(__name__)


def _window():
    return resolve_window(
        period=request.args.get("period"),
        start=request.args.get("start"),
        end=request.args.get("end"),
    )


def _envelope(label, start, end, payload):
    return jsonify({
        "period": label,
        "start": start.isoformat() + "Z",
        "end": end.isoformat() + "Z",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        **payload,
    })


@brain_bp.route("/metrics/summary", methods=["GET"])
@admin_required
@handle_errors("load metrics summary")
def metrics_summary():
    label, start, end = _window()
    return _envelope(label, start, end, queries.summary(start, end))


@brain_bp.route("/metrics/ai", methods=["GET"])
@admin_required
@handle_errors("load AI usage metrics")
def metrics_ai():
    label, start, end = _window()
    return _envelope(label, start, end, {
        **queries.ai_usage(start, end),
        "reliability": queries.ai_reliability(start, end),
    })


@brain_bp.route("/metrics/engagement", methods=["GET"])
@admin_required
@handle_errors("load engagement metrics")
def metrics_engagement():
    label, start, end = _window()
    return _envelope(label, start, end, queries.engagement(start, end))


@brain_bp.route("/metrics/quality", methods=["GET"])
@admin_required
@handle_errors("load quality metrics")
def metrics_quality():
    label, start, end = _window()
    return _envelope(label, start, end, queries.quality(start, end))


@brain_bp.route("/metrics/throughput", methods=["GET"])
@admin_required
@handle_errors("load throughput metrics")
def metrics_throughput():
    label, start, end = _window()
    return _envelope(label, start, end, queries.throughput(start, end))


@brain_bp.route("/metrics/content", methods=["GET"])
@admin_required
@handle_errors("load content metrics")
def metrics_content():
    label, start, end = _window()
    return _envelope(label, start, end, queries.content(start, end))


@brain_bp.route("/metrics/activity", methods=["GET"])
@admin_required
@handle_errors("load activity metrics")
def metrics_activity():
    label, start, end = _window()
    return _envelope(label, start, end, queries.activity(start, end))


@brain_bp.route("/metrics/system", methods=["GET"])
@admin_required
@handle_errors("load system metrics")
def metrics_system():
    label, start, end = _window()
    return _envelope(label, start, end, queries.system(start, end))


@brain_bp.route("/metrics/digest", methods=["GET"])
@admin_required
@handle_errors("load metrics digest")
def metrics_digest():
    label, start, end = _window()
    s = queries.summary(start, end)
    return _envelope(label, start, end, {
        "text": queries.digest_text(label, s),
        "summary": s,
    })
