"""Read-only aggregation queries behind the /brain/metrics endpoints.

Every function takes a resolved ``[start, end)`` naive-UTC window and returns a
plain dict/list structure (JSON-ready, agent-consumable). Grouping is done with
``func.count``/``func.sum`` where a single dimension suffices, and in Python when
day-bucketing (buckets are Mountain-time days, not portable to SQL).

AI spend comes straight from the unified ``ai_usage`` ledger (one row per LLM call,
written by app/services/ai_usage.record). Everything else reads the feature tables
that already carry a who-column + timestamp.
"""
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.models import (
    db, User, AiUsage,
    BBDrawingReview, BBReviewFeedback,
    ReleasePhoto, BoardItemPhoto, ReleaseDrawingVersion,
    BoardActivity, DrawingVersionComment, Notification,
    ReleaseEvents, SubmittalEvents, Meeting, MeetingLearning, ChecklistItem,
    SyncOperation, SyncStatus, SystemLogs, WebhookReceipt, TrelloOutbox, ProcoreOutbox,
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
        "storage": _storage(start, end),
        "mentions_read": _mentions_read(start, end),
    }


def _bytes(model, start=None, end=None):
    """Sum file_size_bytes for a file model, optionally within a window."""
    q = db.session.query(func.coalesce(func.sum(model.file_size_bytes), 0)).filter(
        model.is_deleted.is_(False)
    )
    if start is not None:
        q = q.filter(model.uploaded_at >= start, model.uploaded_at < end)
    return int(q.scalar() or 0)


def _storage(start, end):
    """Disk footprint of user-uploaded files: added this window + total all-time."""
    file_models = {
        "release_photos": ReleasePhoto,
        "board_photos": BoardItemPhoto,
        "drawing_versions": ReleaseDrawingVersion,
    }
    added = {k: _bytes(m, start, end) for k, m in file_models.items()}
    total = {k: _bytes(m) for k, m in file_models.items()}
    return {
        "added_bytes": {**added, "all": sum(added.values())},
        "total_bytes": {**total, "all": sum(total.values())},
    }


def _mentions_read(start, end):
    """Read vs unread for @mention notifications created in the window (engagement)."""
    rows = _count_by(
        db.session.query(Notification.is_read, func.count(Notification.id))
        .filter(Notification.type == "mention",
                Notification.created_at >= start, Notification.created_at < end)
        .group_by(Notification.is_read)
    )
    # SQLite renders booleans as '0'/'1'; Postgres as 'true'/'false' — handle both.
    read = int(rows.get("1", 0)) + int(rows.get("true", 0)) + int(rows.get("True", 0))
    unread = int(rows.get("0", 0)) + int(rows.get("false", 0)) + int(rows.get("False", 0))
    total = read + unread
    return {"read": read, "unread": unread,
            "read_rate": round(read / total, 3) if total else None}


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
    # Render enum keys (e.g. SyncStatus) by their string value, not "SyncStatus.X".
    return {str(getattr(k, "value", k)): int(v) for k, v in query.all()}


def _age_minutes(ts):
    """Minutes between a naive-UTC timestamp and now (None if ts is None)."""
    if ts is None:
        return None
    return round((datetime.utcnow() - ts).total_seconds() / 60.0, 1)


def _outbox_delivery(model, start, end):
    """Windowed delivery outcome for one outbox: created in-window, by status.

    `failed` = retries exhausted → a lost outbound update (an ERROR per the logging
    standard). success_rate is completed / (completed + failed).
    """
    by_status = _count_by(
        db.session.query(model.status, func.count(model.id))
        .filter(model.created_at >= start, model.created_at < end)
        .group_by(model.status)
    )
    completed = int(by_status.get("completed", 0))
    failed = int(by_status.get("failed", 0))
    denom = completed + failed
    return {
        "by_status": by_status,
        "completed": completed,
        "failed": failed,
        "pending": int(by_status.get("pending", 0)),
        "success_rate": round(completed / denom, 3) if denom else None,
    }


def system(start, end):
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
    # Top failing operations — the actionable slice of the error count.
    top_errors = [
        {"operation": op, "category": cat, "count": int(n)}
        for op, cat, n in (
            db.session.query(SystemLogs.operation, SystemLogs.category, func.count(SystemLogs.id))
            .filter(SystemLogs.timestamp >= start, SystemLogs.timestamp < end,
                    SystemLogs.level == "ERROR")
            .group_by(SystemLogs.operation, SystemLogs.category)
            .order_by(func.count(SystemLogs.id).desc()).limit(5).all()
        )
    ]
    webhooks = (
        db.session.query(func.count(WebhookReceipt.id))
        .filter(WebhookReceipt.received_at >= start, WebhookReceipt.received_at < end)
        .scalar()
    )
    # Current backlog (all-time state) plus windowed delivery outcome.
    backlog, delivery = {}, {}
    for name, model in (("trello", TrelloOutbox), ("procore", ProcoreOutbox)):
        backlog[name] = _count_by(
            db.session.query(model.status, func.count(model.id)).group_by(model.status)
        )
        delivery[name] = _outbox_delivery(model, start, end)

    # Data freshness — how stale is the last successful sync / webhook (relative to now).
    last_sync = (
        db.session.query(func.max(SyncOperation.completed_at))
        .filter(SyncOperation.status == SyncStatus.COMPLETED).scalar()
    )
    last_webhook = db.session.query(func.max(WebhookReceipt.received_at)).scalar()

    return {
        "sync_operations": {
            "by_status": sync_by_status,
            "avg_duration_seconds": round(avg_sync, 2) if avg_sync is not None else None,
        },
        "logs_by_level": logs_by_level,
        "errors": int(logs_by_level.get("ERROR", 0)),
        "top_errors": top_errors,
        "webhooks_received": int(webhooks or 0),
        "outbox_backlog": backlog,
        "outbox_delivery": delivery,
        "freshness": {
            "last_sync_at": last_sync.isoformat() + "Z" if last_sync else None,
            "last_sync_age_minutes": _age_minutes(last_sync),
            "last_webhook_at": last_webhook.isoformat() + "Z" if last_webhook else None,
            "last_webhook_age_minutes": _age_minutes(last_webhook),
        },
    }


# ---------------------------------------------------------------------------
# Engagement (adoption / active users)
# ---------------------------------------------------------------------------

def _distinct_user_ids(ucol, tcol, start, end, *filters):
    """Distinct non-null user ids from a table within the window. Degrades to empty
    if the table is unavailable (e.g. ai_usage pre-migration)."""
    try:
        q = (db.session.query(ucol)
             .filter(tcol >= start, tcol < end, ucol.isnot(None)))
        for f in filters:
            q = q.filter(f)
        return {uid for (uid,) in q.distinct().all()}
    except SQLAlchemyError:
        db.session.rollback()
        return set()


def engagement(start, end):
    """Who is actually using the system this window.

    ``active_users`` = distinct users who took ANY attributed action (release/
    submittal events, uploads, comments, AI calls, review feedback). ``logins`` =
    users whose ``last_login`` falls in the window — a single overwritten timestamp,
    so it counts users seen at least once, not a per-day series. The roster pairs
    each active user with their action volume and login recency.
    """
    active = set()
    for model in (ReleaseEvents, SubmittalEvents):
        active |= _distinct_user_ids(model.internal_user_id, model.created_at, start, end,
                                     model.is_system_echo.is_(False))
    for ucol, tcol in (
        (ReleasePhoto.uploaded_by_user_id, ReleasePhoto.uploaded_at),
        (BoardItemPhoto.uploaded_by_user_id, BoardItemPhoto.uploaded_at),
        (ReleaseDrawingVersion.uploaded_by_user_id, ReleaseDrawingVersion.uploaded_at),
        (BoardActivity.author_id, BoardActivity.created_at),
        (DrawingVersionComment.author_id, DrawingVersionComment.created_at),
        (BBReviewFeedback.user_id, BBReviewFeedback.created_at),
        (AiUsage.user_id, AiUsage.created_at),
    ):
        active |= _distinct_user_ids(ucol, tcol, start, end)

    login_rows = (User.query
                  .filter(User.last_login >= start, User.last_login < end)
                  .order_by(User.last_login.desc()).all())

    action_counts = defaultdict(int)
    for model in (ReleaseEvents, SubmittalEvents):
        for uid, n in (db.session.query(model.internal_user_id, func.count(model.id))
                       .filter(model.created_at >= start, model.created_at < end,
                               model.is_system_echo.is_(False),
                               model.internal_user_id.isnot(None))
                       .group_by(model.internal_user_id).all()):
            action_counts[uid] += int(n)

    names = _user_names(active | {u.id for u in login_rows})
    last_login = ({u.id: u.last_login for u in User.query.filter(User.id.in_(active)).all()}
                  if active else {})
    roster = sorted(
        [{"user_id": uid, "username": names.get(uid),
          "actions": action_counts.get(uid, 0),
          "last_login": (last_login[uid].isoformat() + "Z") if last_login.get(uid) else None}
         for uid in active],
        key=lambda r: (r["actions"], r["last_login"] or ""), reverse=True)
    return {
        "active_users": len(active),
        "logins_in_window": len(login_rows),
        "roster": roster[:20],
    }


# ---------------------------------------------------------------------------
# AI reliability + latency
# ---------------------------------------------------------------------------

def _avg(values, ndigits=1):
    return round(sum(values) / len(values), ndigits) if values else None


def ai_reliability(start, end):
    """AI failure rates and latency — the health the spend ledger deliberately omits."""
    review_status = _count_by(
        db.session.query(BBDrawingReview.status, func.count(BBDrawingReview.id))
        .filter(BBDrawingReview.created_at >= start, BBDrawingReview.created_at < end)
        .group_by(BBDrawingReview.status))
    r_complete, r_error = int(review_status.get("complete", 0)), int(review_status.get("error", 0))
    r_denom = r_complete + r_error
    review_lat = [
        (c - s).total_seconds()
        for s, c in db.session.query(BBDrawingReview.created_at, BBDrawingReview.completed_at)
        .filter(BBDrawingReview.created_at >= start, BBDrawingReview.created_at < end,
                BBDrawingReview.completed_at.isnot(None)).all()
        if c and s and c >= s
    ]

    meeting_status = _count_by(
        db.session.query(Meeting.extract_status, func.count(Meeting.id))
        .filter(Meeting.extract_started_at >= start, Meeting.extract_started_at < end)
        .group_by(Meeting.extract_status))
    meeting_lat = [
        (e - s).total_seconds()
        for s, e in db.session.query(Meeting.extract_started_at, Meeting.extracted_at)
        .filter(Meeting.extract_started_at >= start, Meeting.extract_started_at < end,
                Meeting.extracted_at.isnot(None)).all()
        if e and s and e >= s
    ]

    stub_meetings = (db.session.query(func.count(Meeting.id))
                     .filter(Meeting.extracted_at >= start, Meeting.extracted_at < end,
                             Meeting.extract_model == "stub").scalar())
    stub_learnings = (db.session.query(func.count(MeetingLearning.id))
                      .filter(MeetingLearning.created_at >= start, MeetingLearning.created_at < end,
                              MeetingLearning.model == "stub").scalar())

    chat_lat = [d for (d,) in _chat_durations(start, end)]

    return {
        "reviews": {
            "by_status": review_status, "complete": r_complete, "error": r_error,
            "success_rate": round(r_complete / r_denom, 3) if r_denom else None,
            "avg_latency_s": _avg(review_lat),
        },
        "meetings": {
            "by_status": meeting_status, "failed": int(meeting_status.get("failed", 0)),
            "avg_latency_s": _avg(meeting_lat),
        },
        "chat": {"avg_latency_ms": _avg(chat_lat, 0)},
        "stub_fallbacks": int(stub_meetings or 0) + int(stub_learnings or 0),
    }


def _chat_durations(start, end):
    try:
        return (db.session.query(AiUsage.duration_ms)
                .filter(AiUsage.feature == "bb_chat", AiUsage.duration_ms.isnot(None),
                        AiUsage.created_at >= start, AiUsage.created_at < end).all())
    except SQLAlchemyError:
        db.session.rollback()
        return []


# ---------------------------------------------------------------------------
# Quality (is the AI trusted — accept rates)
# ---------------------------------------------------------------------------

def quality(start, end):
    """Human accept/reject signal on AI output — the best proxy for usefulness."""
    fb = _count_by(
        db.session.query(BBReviewFeedback.decision, func.count(BBReviewFeedback.id))
        .filter(BBReviewFeedback.created_at >= start, BBReviewFeedback.created_at < end)
        .group_by(BBReviewFeedback.decision))
    fb_acc, fb_rej = int(fb.get("accepted", 0)), int(fb.get("rejected", 0))
    fb_denom = fb_acc + fb_rej

    generated = int(db.session.query(func.count(ChecklistItem.id))
                    .filter(ChecklistItem.created_at >= start,
                            ChecklistItem.created_at < end).scalar() or 0)
    reviewed = _count_by(
        db.session.query(ChecklistItem.status, func.count(ChecklistItem.id))
        .filter(ChecklistItem.reviewed_at >= start, ChecklistItem.reviewed_at < end)
        .group_by(ChecklistItem.status))
    t_acc = int(reviewed.get("accepted", 0)) + int(reviewed.get("done", 0))
    t_rej = int(reviewed.get("rejected", 0))
    t_denom = t_acc + t_rej

    return {
        "bb_review_findings": {
            "accepted": fb_acc, "rejected": fb_rej,
            "accept_rate": round(fb_acc / fb_denom, 3) if fb_denom else None,
        },
        "meeting_todos": {
            "generated": generated, "accepted": t_acc, "rejected": t_rej,
            "accept_rate": round(t_acc / t_denom, 3) if t_denom else None,
            "by_status": reviewed,
        },
    }


# ---------------------------------------------------------------------------
# Throughput / cycle time (release flow)
# ---------------------------------------------------------------------------

# The "complete zone" a release lands in (see the neutralize_install_date cascade).
COMPLETE_STAGES = {"Complete", "Install Complete"}


def throughput(start, end):
    """Release flow: created vs completed, and average dwell time per stage.

    Dwell is derived by pairing consecutive ``update_stage`` events for the same
    release; only transitions observed WITHIN the window are counted, so dwell is a
    windowed approximation, not a full-history cycle time.
    """
    days = bucket_dates(start, end)

    created_ts = [t for (t,) in db.session.query(ReleaseEvents.created_at)
                  .filter(ReleaseEvents.action == "created",
                          ReleaseEvents.is_system_echo.is_(False),
                          ReleaseEvents.created_at >= start,
                          ReleaseEvents.created_at < end).all()]

    stage_events = (db.session.query(
        ReleaseEvents.job, ReleaseEvents.release, ReleaseEvents.created_at, ReleaseEvents.payload)
        .filter(ReleaseEvents.action == "update_stage", ReleaseEvents.is_system_echo.is_(False),
                ReleaseEvents.created_at >= start, ReleaseEvents.created_at < end)
        .order_by(ReleaseEvents.job, ReleaseEvents.release, ReleaseEvents.created_at).all())

    completed_ts, dwell_sum, dwell_n = [], defaultdict(float), defaultdict(int)
    prev_key = prev = None
    for job, rel, ts, payload in stage_events:
        payload = payload or {}
        to_stage = payload.get("to")
        if to_stage in COMPLETE_STAGES:
            completed_ts.append(ts)
        key = (job, rel)
        if prev_key == key and prev is not None:
            prev_ts, prev_to = prev
            if prev_to:
                d = (ts - prev_ts).total_seconds() / 86400.0
                if d >= 0:
                    dwell_sum[prev_to] += d
                    dwell_n[prev_to] += 1
        prev_key, prev = key, (ts, to_stage)

    created_by_day, completed_by_day = defaultdict(int), defaultdict(int)
    for t in created_ts:
        created_by_day[mountain_date_key(t)] += 1
    for t in completed_ts:
        completed_by_day[mountain_date_key(t)] += 1

    stage_dwell = sorted(
        [{"stage": s, "avg_days": round(dwell_sum[s] / dwell_n[s], 1), "transitions": dwell_n[s]}
         for s in dwell_n],
        key=lambda r: r["avg_days"], reverse=True)

    return {
        "releases_created": len(created_ts),
        "releases_completed": len(completed_ts),
        "net": len(created_ts) - len(completed_ts),
        "by_day": [{"date": d, "created": created_by_day.get(d, 0),
                    "completed": completed_by_day.get(d, 0)} for d in days],
        "stage_dwell_days": stage_dwell,
    }


# ---------------------------------------------------------------------------
# Summary + digest
# ---------------------------------------------------------------------------

def _pct(rate):
    return f"{round(rate * 100)}%" if rate is not None else "n/a"


def summary(start, end):
    ai = ai_usage(start, end)
    con = content(start, end)
    act = activity(start, end)
    sysm = system(start, end)
    eng = engagement(start, end)
    qual = quality(start, end)
    rel = ai_reliability(start, end)
    tp = throughput(start, end)
    t = ai["totals"]
    ct = con["totals"]
    return {
        "engagement": {
            "active_users": eng["active_users"],
            "logins": eng["logins_in_window"],
        },
        "ai": {
            "calls": t["calls"], "cost_usd": t["cost_usd"],
            "input_tokens": t["input_tokens"], "output_tokens": t["output_tokens"],
            "success_rate": rel["reviews"]["success_rate"],
            "failures": rel["reviews"]["error"] + rel["meetings"]["failed"] + rel["stub_fallbacks"],
        },
        "quality": {
            "bb_accept_rate": qual["bb_review_findings"]["accept_rate"],
            "todo_accept_rate": qual["meeting_todos"]["accept_rate"],
        },
        "content": {
            "photos": ct["release_photos"] + ct["board_photos"],
            "drawings": ct["drawing_versions"],
            "comments": ct["board_comments"] + ct["drawing_comments"],
            "reviews": ct["bb_reviews"],
            "mentions": ct["mentions"],
            "storage_added_bytes": con["storage"]["added_bytes"]["all"],
        },
        "activity": {"human_actions": act["total"]},
        "throughput": {
            "releases_created": tp["releases_created"],
            "releases_completed": tp["releases_completed"],
        },
        "system": {
            "errors": sysm["errors"],
            "sync_ops": sum(sysm["sync_operations"]["by_status"].values()),
            "webhooks": sysm["webhooks_received"],
            "last_sync_age_minutes": sysm["freshness"]["last_sync_age_minutes"],
        },
    }


def digest_text(period_label, s):
    """A one-line human/agent-readable roll-up of the summary dict ``s``."""
    eng, ai, con, act, tp, sysm, qual = (
        s["engagement"], s["ai"], s["content"], s["activity"],
        s["throughput"], s["system"], s["quality"])
    return (
        f"This {period_label}: {eng['active_users']} active users · "
        f"{ai['calls']} AI calls · ${ai['cost_usd']:.2f} "
        f"(BB accept {_pct(qual['bb_accept_rate'])}, {ai['failures']} AI failures) · "
        f"{con['photos']} photos · {con['drawings']} drawings · "
        f"{con['reviews']} BB reviews · {act['human_actions']} human actions · "
        f"{tp['releases_created']} releases created / {tp['releases_completed']} completed · "
        f"{sysm['errors']} errors."
    )
