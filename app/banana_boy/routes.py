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
from app.models import ChatMessage, db

logger = get_logger(__name__)

MAX_MESSAGE_LENGTH = 8000
GMAIL_CONTEXT_MAX_CHARS = 4000


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


@banana_boy_bp.route("/messages", methods=["GET"])
@login_required
def list_messages():
    user = get_current_user()
    rows = (
        ChatMessage.query.filter_by(user_id=user.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
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

    user_turn = ChatMessage(user_id=user.id, role="user", content=message)
    db.session.add(user_turn)
    db.session.commit()

    history = [
        {"role": m.role, "content": m.content}
        for m in ChatMessage.query.filter_by(user_id=user.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    ]

    gmail_block = ""
    if user.gmail_credentials is not None:
        try:
            threads = fetch_recent_threads(user.id, max_results=10)
            gmail_block = _format_gmail_block(threads)
        except Exception as exc:  # noqa: BLE001 — never let Gmail issues kill chat
            logger.warning("gmail_context_fetch_failed", user_id=user.id, error=str(exc))

    try:
        reply_text = generate_reply(
            history,
            extra_system_context=gmail_block,
            tool_context={"user_id": user.id},
        )
    except BananaBoyConfigError as exc:
        logger.error("Banana Boy not configured", error=str(exc))
        return jsonify({"error": "assistant is not configured"}), 503
    except BananaBoyAPIError as exc:
        logger.error("Banana Boy upstream failed", error=str(exc))
        return jsonify({"error": "assistant is unavailable"}), 502

    assistant_turn = ChatMessage(user_id=user.id, role="assistant", content=reply_text)
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
