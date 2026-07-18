"""Data lake (Hive Mind) HTTP surface.

Admin-only endpoints for triggering ingestion. The on-demand mail pull is the
seam Banana Boy will call when a user says "read the email I forwarded you"
(the BB tool wiring lands in a later increment); for now it is exercisable
directly for testing/operations.
"""
from flask import Blueprint, Response, current_app, jsonify, request

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


@lake_bp.route("/graph/notifications", methods=["POST"])
def graph_notifications():
    """Receive Microsoft Graph change notifications for the BB mailbox (PUSH path).

    Unauthenticated from Flask's side — Graph doesn't carry a session; authenticity
    is proven by the per-notification `clientState` secret, verified downstream in
    handle_notification. Two request shapes arrive here:

    1. Validation handshake: on subscription create/renew, Graph POSTs with a
       `?validationToken=...` query param and expects it echoed back verbatim as
       text/plain 200 within ~10s. This branch MUST stay first and trivial — any
       work before the echo risks blowing the window and failing the create.
    2. Real notification: a JSON body {"value": [ ... ]}. We land each message and
       return 202 promptly (Graph retries/kills subscriptions on slow acks).
    """
    validation_token = request.args.get("validationToken")
    if validation_token is not None:
        return Response(validation_token, mimetype="text/plain", status=200)

    payload = request.get_json(silent=True) or {}
    from app.lake.ingest import graph_subscription

    try:
        summary = graph_subscription.handle_notification(payload)
    except Exception:
        # Never fail the ack — a 5xx makes Graph retry then drop the subscription.
        # The poll floor still catches anything we miss here.
        logger.error("graph_notifications_handler_failed", exc_info=True)
        return "", 202

    logger.info("graph_notifications_processed", **summary)
    return "", 202
