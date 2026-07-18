"""Unified AI-usage ledger: the one writer every LLM call site uses.

Each feature that calls Claude (bb_chat, meetings, meeting_learning, pdf_review,
material_orders) appends ONE `AiUsage` row here so system-wide spend has a single
source of truth (`app/brain/metrics` reads only this table).

Two hard rules:
  1. **Writing the ledger row must never break the feature that made the AI call.**
     `record()` catches and logs any failure and returns None — a missing table
     during a mid-deploy window, or any DB hiccup, degrades to "no metrics row",
     never to a broken chat turn / review / extraction.
  2. **Own-transaction commit** (mirrors `SystemLogService.log_error`): callers
     invoke `record()` right after their own primary commit, so the session is
     clean and the ledger row rides its own transaction.

Cost is computed once, here, from the shared bb_chat pricing table (same rates the
Phase-1 aggregator used), including cache-read/write multipliers.
"""
from app.logging_config import get_logger
from app.models import db, AiUsage
from app.brain.bb_chat.pricing import (
    _price, _CACHE_READ_MULTIPLIER, _CACHE_WRITE_MULTIPLIER,
)

logger = get_logger(__name__)


def compute_cost(model, input_tokens=0, output_tokens=0,
                 cache_read_tokens=0, cache_write_tokens=0):
    """USD cost for a call, from token counts and the shared pricing table."""
    pin, pout = _price(model)
    cost = (
        (input_tokens or 0) / 1e6 * pin
        + (output_tokens or 0) / 1e6 * pout
        + (cache_read_tokens or 0) / 1e6 * pin * _CACHE_READ_MULTIPLIER
        + (cache_write_tokens or 0) / 1e6 * pin * _CACHE_WRITE_MULTIPLIER
    )
    return round(cost, 6)


def record(feature, *, model=None, input_tokens=0, output_tokens=0,
           cache_read_tokens=0, cache_write_tokens=0, cost_usd=None,
           duration_ms=None, user_id=None, entity_type=None, entity_id=None,
           request_id=None, created_at=None, commit=True):
    """Append one row to the ai_usage ledger. Best-effort — never raises.

    Pass ``cost_usd`` when the caller already computed it (bb_chat carries a
    per-turn cost); otherwise it is derived from the token counts. ``commit``
    defaults True: call this AFTER your own commit so the session is clean and the
    ledger row is isolated in its own transaction.
    """
    try:
        if cost_usd is None:
            cost_usd = compute_cost(model, input_tokens, output_tokens,
                                    cache_read_tokens, cache_write_tokens)
        row = AiUsage(
            feature=feature,
            model=model,
            user_id=user_id,
            anthropic_request_id=request_id,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            cache_read_tokens=cache_read_tokens or 0,
            cache_write_tokens=cache_write_tokens or 0,
            cost_usd=cost_usd or 0.0,
            duration_ms=duration_ms,
            entity_type=entity_type,
            entity_id=(str(entity_id) if entity_id is not None else None),
        )
        if created_at is not None:
            row.created_at = created_at
        db.session.add(row)
        if commit:
            db.session.commit()
        return row
    except Exception as e:  # noqa: BLE001 — metrics must never break the feature
        logger.error("ai_usage_record_failed", feature=feature,
                     error=str(e), error_type=type(e).__name__, exc_info=True)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
