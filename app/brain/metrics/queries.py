"""Read-only aggregation queries behind the /brain/metrics endpoints.

Every function takes a resolved ``[start, end)`` naive-UTC window and returns a
plain dict/list structure (JSON-ready, agent-consumable). Grouping is done with
``func.count``/``func.sum`` where a single dimension suffices, and in Python when
day-bucketing (buckets are Mountain-time days, not portable to SQL).

AI usage is the one heterogeneous domain: cost/token columns live on four
different tables today. ``ai_usage`` normalizes them into one shape that maps 1:1
onto the future ``ai_usage`` ledger, so Phase 2 swaps ``_ai_rows`` for a single
-table query and nothing downstream changes.
"""
from collections import defaultdict

from sqlalchemy.exc import SQLAlchemyError

from app.models import (
    db, User, AiUsage,
    BBDrawingReview, BBReviewFeedback,
    ReleasePhoto, BoardItemPhoto, ReleaseDrawingVersion,
    BoardActivity, DrawingVersionComment, Notification,
    ReleaseEvents, SubmittalEvents,
    SyncOperation, SystemLogs, WebhookReceipt, TrelloOutbox, ProcoreOutbox,
)
from app.logging_config import get_logger

from .timeframe import mountain_date_key, bucket_dates

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _user_names(ids):
    """Batch-resolve user_id -> display name (First Last, or username). One query."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    names = {}
    for u in User.query.filter(User.id.in_(ids)).all():
        first = (u.first_name or "").strip()
        last = (u.last_name or "").strip()
        names[u.id] = (f"{first} {last}".strip()) or u.username
    return names


def _sorted_user_list(counts, names, value_key="count"):
    """counts: {user_id: number} -> descending list with resolved usernames."""
    rows = [
        {"user_id": uid, "username": names.get(uid), value_key: val}
        for uid, val in counts.items()
    ]
    rows.sort(key=lambda r: (r[value_key] or 0), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# AI usage
# ---------------------------------------------------------------------------

def _ai_rows(start, end):
    """AI spend for the window, straight from the unified ``ai_usage`` ledger.

    Every LLM call site writes one row here (see app/services/ai_usage.record),
    so this is a single-table read — material_orders included. Cost is already
    computed at write time.

    Degrades gracefully if the table doesn't exist yet (code deployed before the
    migration ran): logs once and returns no rows, so the rest of the dashboard
    (content/activity/system) still renders instead of 500ing.
    """
    try:
        q = AiUsage.query.filter(AiUsage.created_at >= start, AiUsage.created_at < end)
        rows = q.all()
    except SQLAlchemyError as e:
        logger.warning("ai_usage_table_unavailable", error=str(e),
                       hint="run migrations/add_ai_usage_table.py")
        db.session.rollback()
        return []
    return [{
        "feature": r.feature, "user_id": r.user_id, "model": r.model,
        "input_tokens": r.input_tokens or 0, "output_tokens": r.output_tokens or 0,
        "cache_read_tokens": r.cache_read_tokens or 0,
        "cache_write_tokens": r.cache_write_tokens or 0,
        "cost_usd": r.cost_usd or 0.0, "duration_ms": r.duration_ms,
        "created_at": r.created_at,
    } for r in rows]


_AI_TOKEN_KEYS = (
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
)


def _blank_ai_bucket():
    b = {k: 0 for k in _AI_TOKEN_KEYS}
    b["calls"] = 0
    b["cost_usd"] = 0.0
    return b


def _add_ai(bucket, row):
    bucket["calls"] += 1
    for k in _AI_TOKEN_KEYS:
        bucket[k] += row[k]
    bucket["cost_usd"] = round(bucket["cost_usd"] + (row["cost_usd"] or 0.0), 6)


def ai_usage(start, end):
    rows = _ai_rows(start, end)
    days = bucket_dates(start, end)

    totals = _blank_ai_bucket()
    by_feature, by_model, by_user, by_day = {}, {}, {}, {}
    dur_sum, dur_n = 0, 0

    for r in rows:
        _add_ai(totals, r)
        _add_ai(by_feature.setdefault(r["feature"], _blank_ai_bucket()), r)
        _add_ai(by_model.setdefault(r["model"] or "unknown", _blank_ai_bucket()), r)
        if r["user_id"] is not None:
            _add_ai(by_user.setdefault(r["user_id"], _blank_ai_bucket()), r)
        _add_ai(by_day.setdefault(mountain_date_key(r["created_at"]), _blank_ai_bucket()), r)
        if r["duration_ms"] is not None:
            dur_sum += r["duration_ms"]
            dur_n += 1

    totals["avg_duration_ms"] = round(dur_sum / dur_n) if dur_n else None
    names = _user_names(by_user.keys())

    def _named(mapping, key):
        return [dict({key: k}, **v) for k, v in
                sorted(mapping.items(), key=lambda kv: kv[1]["cost_usd"], reverse=True)]

    return {
        "totals": totals,
        "by_feature": _named(by_feature, "feature"),
        "by_model": _named(by_model, "model"),
        "by_user": sorted(
            [dict({"user_id": uid, "username": names.get(uid)}, **v) for uid, v in by_user.items()],
            key=lambda r: r["cost_usd"], reverse=True,
        ),
        "by_day": [dict({"date": d}, **by_day.get(d, _blank_ai_bucket())) for d in days],
    }


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

def _event_metric(pairs, days, names=None):
    """pairs: iterable of (timestamp, user_id) -> {count, by_user[], by_day[]}."""
    by_user, by_day = defaultdict(int), defaultdict(int)
    total = 0
    for ts, uid in pairs:
        total += 1
        by_day[mountain_date_key(ts)] += 1
        if uid is not None:
            by_user[uid] += 1
    names = names if names is not None else _user_names(by_user.keys())
    return {
        "count": total,
        "by_user": _sorted_user_list(by_user, names),
        "by_day": [{"date": d, "count": by_day.get(d, 0)} for d in days],
    }


def _fetch_pairs(ts_col, user_col, start, end, *filters):
    q = db.session.query(ts_col, user_col).filter(ts_col >= start, ts_col < end)
    for f in filters:
        q = q.filter(f)
    return q.all()


def content(start, end):
    days = bucket_dates(start, end)
    sources = {
        "release_photos": _fetch_pairs(
            ReleasePhoto.uploaded_at, ReleasePhoto.uploaded_by_user_id, start, end,
            ReleasePhoto.is_deleted.is_(False)),
        "board_photos": _fetch_pairs(
            BoardItemPhoto.uploaded_at, BoardItemPhoto.uploaded_by_user_id, start, end,
            BoardItemPhoto.is_deleted.is_(False)),
        "drawing_versions": _fetch_pairs(
            ReleaseDrawingVersion.uploaded_at, ReleaseDrawingVersion.uploaded_by_user_id,
            start, end, ReleaseDrawingVersion.is_deleted.is_(False)),
        "board_comments": _fetch_pairs(
            BoardActivity.created_at, BoardActivity.author_id, start, end,
            BoardActivity.type == "comment"),
        "drawing_comments": _fetch_pairs(
            DrawingVersionComment.created_at, DrawingVersionComment.author_id, start, end),
        "bb_reviews": _fetch_pairs(
            BBDrawingReview.created_at, BBDrawingReview.requested_by_user_id, start, end),
        "review_feedback": _fetch_pairs(
            BBReviewFeedback.created_at, BBReviewFeedback.user_id, start, end),
        # Recipient-only: Notification has no actor FK, so by_user here is who was
        # mentioned, not who mentioned. Surfaced as volume; documented in the API.
        "mentions": _fetch_pairs(
            Notification.created_at, Notification.user_id, start, end,
            Notification.type == "mention"),
    }
    all_ids = {uid for pairs in sources.values() for _, uid in pairs}
    names = _user_names(all_ids)
    by_type = {k: _event_metric(v, days, names) for k, v in sources.items()}
    return {
        "by_type": by_type,
        "totals": {k: v["count"] for k, v in by_type.items()},
    }


# ---------------------------------------------------------------------------
# Activity (human release/submittal actions)
# ---------------------------------------------------------------------------

def _activity_rows(model, start, end):
    return (
        db.session.query(model.created_at, model.internal_user_id, model.action)
        .filter(
            model.created_at >= start, model.created_at < end,
            model.is_system_echo.is_(False),
        )
        .all()
    )


def activity(start, end):
    days = bucket_dates(start, end)
    rows = _activity_rows(ReleaseEvents, start, end) + _activity_rows(SubmittalEvents, start, end)

    by_action, by_user, by_day = defaultdict(int), defaultdict(int), defaultdict(int)
    for ts, uid, action in rows:
        by_action[action] += 1
        by_day[mountain_date_key(ts)] += 1
        if uid is not None:
            by_user[uid] += 1

    names = _user_names(by_user.keys())
    return {
        "total": len(rows),
        "by_action": sorted(
            [{"action": a, "count": c} for a, c in by_action.items()],
            key=lambda r: r["count"], reverse=True),
        "by_user": _sorted_user_list(by_user, names),
        "by_day": [{"date": d, "count": by_day.get(d, 0)} for d in days],
    }


# ---------------------------------------------------------------------------
# System health
# ---------------------------------------------------------------------------

def _count_by(query):
    return {str(k): int(v) for k, v in query.all()}


def system(start, end):
    from sqlalchemy import func

    sync_by_status = _count_by(
        db.session.query(SyncOperation.status, func.count(SyncOperation.id))
        .filter(SyncOperation.started_at >= start, SyncOperation.started_at < end)
        .group_by(SyncOperation.status)
    )
    avg_sync = (
        db.session.query(func.avg(SyncOperation.duration_seconds))
        .filter(SyncOperation.started_at >= start, SyncOperation.started_at < end)
        .scalar()
    )
    logs_by_level = _count_by(
        db.session.query(SystemLogs.level, func.count(SystemLogs.id))
        .filter(SystemLogs.timestamp >= start, SystemLogs.timestamp < end)
        .group_by(SystemLogs.level)
    )
    webhooks = (
        db.session.query(func.count(WebhookReceipt.id))
        .filter(WebhookReceipt.received_at >= start, WebhookReceipt.received_at < end)
        .scalar()
    )
    # Outbox backlog is a current-state signal, not windowed.
    outbox = {}
    for name, model in (("trello", TrelloOutbox), ("procore", ProcoreOutbox)):
        outbox[name] = _count_by(
            db.session.query(model.status, func.count(model.id)).group_by(model.status)
        )

    return {
        "sync_operations": {
            "by_status": sync_by_status,
            "avg_duration_seconds": round(avg_sync, 2) if avg_sync is not None else None,
        },
        "logs_by_level": logs_by_level,
        "errors": int(logs_by_level.get("ERROR", 0)),
        "webhooks_received": int(webhooks or 0),
        "outbox_backlog": outbox,
    }


# ---------------------------------------------------------------------------
# Summary + digest
# ---------------------------------------------------------------------------

def summary(start, end):
    ai = ai_usage(start, end)
    con = content(start, end)
    act = activity(start, end)
    sysm = system(start, end)
    t = ai["totals"]
    ct = con["totals"]
    return {
        "ai": {
            "calls": t["calls"], "cost_usd": t["cost_usd"],
            "input_tokens": t["input_tokens"], "output_tokens": t["output_tokens"],
        },
        "content": {
            "photos": ct["release_photos"] + ct["board_photos"],
            "drawings": ct["drawing_versions"],
            "comments": ct["board_comments"] + ct["drawing_comments"],
            "reviews": ct["bb_reviews"],
            "mentions": ct["mentions"],
        },
        "activity": {"human_actions": act["total"]},
        "system": {
            "errors": sysm["errors"],
            "sync_ops": sum(sysm["sync_operations"]["by_status"].values()),
            "webhooks": sysm["webhooks_received"],
        },
    }


def digest_text(period_label, s):
    """A one-line human/agent-readable roll-up of the summary dict ``s``."""
    ai, con, act, sysm = s["ai"], s["content"], s["activity"], s["system"]
    return (
        f"This {period_label}: {ai['calls']} AI calls · ${ai['cost_usd']:.2f} "
        f"({ai['input_tokens']:,} in / {ai['output_tokens']:,} out tok) · "
        f"{con['photos']} photos · {con['drawings']} drawings · "
        f"{con['comments']} comments · {con['reviews']} BB reviews · "
        f"{act['human_actions']} human actions · {sysm['errors']} errors."
    )
