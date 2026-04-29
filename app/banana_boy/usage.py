"""Persistence helper for Banana Boy API usage records.

Each upstream API call (Anthropic chat, Whisper, TTS) appends a dict to a
`usage_sink` list passed by the caller. Once the chat turn is committed,
`persist_usage()` writes them to `banana_boy_usage`, attaching the assistant
ChatMessage id when one exists.
"""
from app.logging_config import get_logger
from app.models import BananaBoyUsage, db

logger = get_logger(__name__)


def persist_usage(usage_sink, *, user_id: int, chat_message_id: int | None = None) -> int:
    """Insert a usage row per record. Returns the count written.

    Failures are logged but never raise — usage tracking must not break chat.
    """
    if not usage_sink:
        return 0
    try:
        rows = []
        for rec in usage_sink:
            rows.append(BananaBoyUsage(
                user_id=user_id,
                chat_message_id=chat_message_id,
                provider=rec.get("provider"),
                operation=rec.get("operation"),
                model=rec.get("model"),
                iteration=rec.get("iteration"),
                duration_ms=int(rec.get("duration_ms") or 0),
                input_tokens=rec.get("input_tokens"),
                output_tokens=rec.get("output_tokens"),
                cache_read_tokens=rec.get("cache_read_tokens"),
                cache_creation_tokens=rec.get("cache_creation_tokens"),
                input_chars=rec.get("input_chars"),
                output_bytes=rec.get("output_bytes"),
                audio_seconds=rec.get("audio_seconds"),
                audio_bytes=rec.get("audio_bytes"),
                cost_usd=rec.get("cost_usd"),
                payload=rec.get("payload"),
            ))
        db.session.add_all(rows)
        db.session.commit()
        logger.info(
            "banana_boy_usage_persisted",
            user_id=user_id,
            chat_message_id=chat_message_id,
            rows=len(rows),
            total_cost_usd=sum((r.cost_usd or 0) for r in rows),
        )
        return len(rows)
    except Exception as exc:  # noqa: BLE001 — never break chat on usage failure
        logger.warning("banana_boy_usage_persist_failed", error=str(exc), exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0
