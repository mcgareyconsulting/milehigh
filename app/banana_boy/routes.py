"""Banana Boy chat endpoints."""
import base64

from flask import jsonify, request

from app.auth.utils import get_current_user, login_required
from app.banana_boy import banana_boy_bp
from app.banana_boy.client import (
    BananaBoyAPIError,
    BananaBoyConfigError,
    generate_reply,
)
from app.banana_boy.gmail_client import fetch_recent_threads
from app.banana_boy.usage import persist_usage
from app.banana_boy.voice_client import extract_spoken_block, synthesize, transcribe
from app.logging_config import get_logger
from app.models import ChatMessage, ROLE_ASSISTANT, ROLE_USER, db

logger = get_logger(__name__)

MAX_MESSAGE_LENGTH = 8000
GMAIL_CONTEXT_MAX_CHARS = 4000
HISTORY_LIMIT = 30
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # Whisper's hard cap


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


def _run_chat_turn(user, user_text: str, *, usage_sink: list | None = None,
                   voice_mode: bool = False) -> ChatMessage:
    """Persist a user turn, run the agent, persist the reply, return the assistant row.

    Raises BananaBoyConfigError / BananaBoyAPIError; the user row is committed before
    the upstream call so partial-failure history is preserved (tests rely on this).
    If `usage_sink` is given, Anthropic per-call usage is appended to it.
    When `voice_mode=True`, the trailing <spoken>...</spoken> block is stripped
    from the persisted chat content and stashed on the returned object as
    `_spoken_text` for the voice route to feed to TTS.
    """
    prior = _recent_history(user.id, HISTORY_LIMIT - 1)
    user_turn = ChatMessage(user_id=user.id, role=ROLE_USER, content=user_text)
    db.session.add(user_turn)
    db.session.commit()

    history = [{"role": m.role, "content": m.content} for m in prior]
    history.append({"role": ROLE_USER, "content": user_text})

    gmail_block = ""
    if user.gmail_credentials is not None:
        try:
            threads = fetch_recent_threads(user.id, max_results=10)
            gmail_block = _format_gmail_block(threads)
        except Exception as exc:  # noqa: BLE001 — never let Gmail issues kill chat
            logger.warning("gmail_context_fetch_failed", user_id=user.id, error=str(exc))

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

    reply_text = generate_reply(
        history,
        extra_system_context=extra_context,
        tool_context={"user_id": user.id},
        usage_sink=usage_sink,
        voice_mode=voice_mode,
    )

    spoken_text = None
    if voice_mode:
        reply_text, spoken_text = extract_spoken_block(reply_text)

    assistant_turn = ChatMessage(user_id=user.id, role=ROLE_ASSISTANT, content=reply_text)
    db.session.add(assistant_turn)
    db.session.commit()
    assistant_turn._spoken_text = spoken_text  # transient; voice_chat reads this

    logger.info(
        "banana_boy_chat",
        user_id=user.id,
        prompt_chars=len(user_text),
        reply_chars=len(reply_text),
        voice_mode=voice_mode,
        has_spoken_block=bool(spoken_text),
    )
    return assistant_turn


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

    usage_sink: list = []
    try:
        assistant_turn = _run_chat_turn(user, message, usage_sink=usage_sink)
    except BananaBoyConfigError as exc:
        logger.error("Banana Boy not configured", error=str(exc))
        persist_usage(usage_sink, user_id=user.id, chat_message_id=None)
        return jsonify({"error": "assistant is not configured"}), 503
    except BananaBoyAPIError as exc:
        logger.error("Banana Boy upstream failed", error=str(exc))
        persist_usage(usage_sink, user_id=user.id, chat_message_id=None)
        return jsonify({"error": "assistant is unavailable"}), 502

    persist_usage(usage_sink, user_id=user.id, chat_message_id=assistant_turn.id)
    return jsonify({"message": assistant_turn.to_dict()})


@banana_boy_bp.route("/voice/chat", methods=["POST"])
@login_required
def voice_chat():
    user = get_current_user()
    audio = request.files.get("audio")
    if audio is None:
        return jsonify({"error": "audio file is required"}), 400

    audio_bytes = audio.read()
    if not audio_bytes:
        return jsonify({"error": "audio file is empty"}), 400
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return jsonify({"error": "audio too large"}), 413

    mime_type = audio.mimetype or "audio/webm"
    filename = audio.filename or "voice.webm"

    usage_sink: list = []
    try:
        transcript = transcribe(audio_bytes, filename=filename, mime_type=mime_type,
                                usage_sink=usage_sink)
    except BananaBoyConfigError as exc:
        logger.error("Voice transcription not configured", error=str(exc))
        persist_usage(usage_sink, user_id=user.id, chat_message_id=None)
        return jsonify({"error": "voice is not configured"}), 503
    except BananaBoyAPIError as exc:
        logger.error("Voice transcription failed", error=str(exc))
        persist_usage(usage_sink, user_id=user.id, chat_message_id=None)
        return jsonify({"error": "transcription failed"}), 502

    transcript = (transcript or "").strip()
    if not transcript:
        persist_usage(usage_sink, user_id=user.id, chat_message_id=None)
        return jsonify({"error": "no speech detected"}), 422
    if len(transcript) > MAX_MESSAGE_LENGTH:
        transcript = transcript[:MAX_MESSAGE_LENGTH]

    try:
        assistant_turn = _run_chat_turn(user, transcript, usage_sink=usage_sink,
                                        voice_mode=True)
    except BananaBoyConfigError as exc:
        logger.error("Banana Boy not configured", error=str(exc))
        persist_usage(usage_sink, user_id=user.id, chat_message_id=None)
        return jsonify({"error": "assistant is not configured"}), 503
    except BananaBoyAPIError as exc:
        logger.error("Banana Boy upstream failed", error=str(exc))
        persist_usage(usage_sink, user_id=user.id, chat_message_id=None)
        return jsonify({"error": "assistant is unavailable"}), 502

    spoken_text = getattr(assistant_turn, "_spoken_text", None)
    # Prefer the model-authored spoken summary; fall back to cleaning the full
    # reply if the model forgot to emit a <spoken> block.
    tts_input = spoken_text or assistant_turn.content
    try:
        audio_mp3 = synthesize(tts_input, usage_sink=usage_sink,
                               already_clean=bool(spoken_text))
        audio_b64 = base64.b64encode(audio_mp3).decode("ascii")
        audio_mime = "audio/mpeg"
    except BananaBoyConfigError as exc:
        logger.warning("Voice synthesis not configured — returning text only", error=str(exc))
        audio_b64 = None
        audio_mime = None
    except BananaBoyAPIError as exc:
        logger.warning("Voice synthesis failed — returning text only", error=str(exc))
        audio_b64 = None
        audio_mime = None

    persist_usage(usage_sink, user_id=user.id, chat_message_id=assistant_turn.id)
    return jsonify({
        "transcript": transcript,
        "message": assistant_turn.to_dict(),
        "audio_b64": audio_b64,
        "audio_mime": audio_mime,
    })


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
