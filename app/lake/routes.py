"""Data lake (Hive Mind) HTTP surface.

Admin-only endpoints for triggering ingestion. The on-demand mail pull is the
seam Banana Boy will call when a user says "read the email I forwarded you"
(the BB tool wiring lands in a later increment); for now it is exercisable
directly for testing/operations.
"""
from flask import Blueprint, current_app, jsonify, request

from app.auth.utils import admin_required
from app.logging_config import get_logger

logger = get_logger(__name__)

lake_bp = Blueprint("lake", __name__)


def _ingest_enabled():
    return bool(current_app.config.get("BB_MAIL_INGEST_ENABLED"))


@lake_bp.route("/ingest/mail/pull", methods=["POST"])
@admin_required
def ingest_mail_pull():
    """Pull fresh mail from the BB mailbox into the lake on demand.

    Optional JSON body: {"query": "<graph search>", "max_results": <int>}.
    Without a query, pulls the most recent inbox messages.
    """
    if not _ingest_enabled():
        return jsonify({"error": "Mail ingest disabled (set BB_MAIL_INGEST_ENABLED=1)"}), 503

    body = request.get_json(silent=True) or {}
    kwargs = {}
    query = body.get("query")
    if query:
        kwargs["query"] = query
    mailbox = body.get("mailbox")
    if mailbox:
        kwargs["mailbox"] = mailbox
    max_results = body.get("max_results")
    if isinstance(max_results, int) and max_results > 0:
        kwargs["max_results"] = max_results

    from app.lake.ingest import m365_mail
    try:
        result = m365_mail.pull(**kwargs)
    except Exception as exc:
        logger.error("ingest_mail_pull_failed", error=str(exc), exc_info=True)
        return jsonify({"error": "Mail pull failed", "detail": str(exc)}), 502

    result.pop("max_occurred_at", None)  # datetime; internal-only
    return jsonify({"status": "ok", **result}), 200
