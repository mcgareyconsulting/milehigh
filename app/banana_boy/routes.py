"""Banana Boy chat endpoints."""
from flask import jsonify, request

from app.auth.utils import get_current_user, login_required
from app.banana_boy import banana_boy_bp
from app.banana_boy.client import (
    BananaBoyAPIError,
    BananaBoyConfigError,
    generate_reply,
)
from app.banana_boy.gmail_client import fetch_recent_threads
from app.logging_config import get_logger
from app.models import ChatMessage, ROLE_ASSISTANT, ROLE_USER, db

logger = get_logger(__name__)

MAX_MESSAGE_LENGTH = 8000
GMAIL_CONTEXT_MAX_CHARS = 4000
HISTORY_LIMIT = 30


def _format_gmail_block(threads):
    if not threads:
        return ""
    lines = ["## Recent Gmail context (last threads, read-only)"]
    for t in threads:
        when = t.get("internal_date") or ""
        sender = t.get("from") or ""
        subject = t.get("subject") or ""
        snippet = (t.get("snippet") or "").replace("\n", " ")
        lines.append(f"- {when} — From: {sender} | Subject: {subject} | snippet: {snippet}")
    lines.append("(End of Gmail context)")
    block = "\n".join(lines)
    if len(block) > GMAIL_CONTEXT_MAX_CHARS:
        block = block[:GMAIL_CONTEXT_MAX_CHARS - 20].rstrip() + "\n… (truncated)"
    return block


def _recent_history(user_id, limit):
    rows = (
        ChatMessage.query.filter_by(user_id=user_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return rows


@banana_boy_bp.route("/messages", methods=["GET"])
@login_required
def list_messages():
    user = get_current_user()
    rows = _recent_history(user.id, HISTORY_LIMIT)
    return jsonify({"messages": [m.to_dict() for m in rows]})


@banana_boy_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({"error": f"message exceeds {MAX_MESSAGE_LENGTH} characters"}), 400

    prior = _recent_history(user.id, HISTORY_LIMIT - 1)
    user_turn = ChatMessage(user_id=user.id, role=ROLE_USER, content=message)
    db.session.add(user_turn)
    db.session.commit()

    history = [{"role": m.role, "content": m.content} for m in prior]
    history.append({"role": ROLE_USER, "content": message})

    gmail_block = ""
    if user.gmail_credentials is not None:
        try:
            threads = fetch_recent_threads(user.id, max_results=10)
            gmail_block = _format_gmail_block(threads)
        except Exception as exc:  # noqa: BLE001 — never let Gmail issues kill chat
            logger.warning("gmail_context_fetch_failed", user_id=user.id, error=str(exc))

    # Identity block — gives the model the user's first name so phrases like
    # "what's in my court" can be translated into search_submittals(ball_in_court=<first_name>).
    identity_lines = ["## Current user"]
    if user.first_name:
        identity_lines.append(f"first_name: {user.first_name}")
    if user.last_name:
        identity_lines.append(f"last_name: {user.last_name}")
    identity_lines.append(f"username: {user.username}")
    identity_block = "\n".join(identity_lines)
    extra_context = identity_block
    if gmail_block:
        extra_context = f"{identity_block}\n\n{gmail_block}"

    try:
        reply_text = generate_reply(
            history,
            extra_system_context=extra_context,
            tool_context={"user_id": user.id},
        )
    except BananaBoyConfigError as exc:
        logger.error("Banana Boy not configured", error=str(exc))
        return jsonify({"error": "assistant is not configured"}), 503
    except BananaBoyAPIError as exc:
        logger.error("Banana Boy upstream failed", error=str(exc))
        return jsonify({"error": "assistant is unavailable"}), 502

    assistant_turn = ChatMessage(user_id=user.id, role=ROLE_ASSISTANT, content=reply_text)
    db.session.add(assistant_turn)
    db.session.commit()

    logger.info(
        "banana_boy_chat",
        user_id=user.id,
        prompt_chars=len(message),
        reply_chars=len(reply_text),
    )
    return jsonify({"message": assistant_turn.to_dict()})


@banana_boy_bp.route("/messages", methods=["DELETE"])
@login_required
def clear_messages():
    user = get_current_user()
    deleted = ChatMessage.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    logger.info("banana_boy_clear", user_id=user.id, deleted=deleted)
    return ("", 204)


@banana_boy_bp.route("/preferences", methods=["PUT"])
@login_required
def set_preferences():
    """Update Banana Boy preferences for the current user.

    Body: {"wants_daily_brief": bool}
    """
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    if "wants_daily_brief" not in payload:
        return jsonify({"error": "wants_daily_brief is required"}), 400
    value = payload.get("wants_daily_brief")
    if not isinstance(value, bool):
        return jsonify({"error": "wants_daily_brief must be a boolean"}), 400

    user.wants_daily_brief = value
    db.session.commit()
    logger.info("banana_boy_preferences_updated",
                user_id=user.id, wants_daily_brief=value)
    return jsonify({"wants_daily_brief": user.wants_daily_brief})
