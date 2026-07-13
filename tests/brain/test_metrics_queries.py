"""Tests for the system-usage metrics aggregation (app/brain/metrics).

Service-level tests exercise the pure query functions against seeded in-memory
rows; two HTTP tests cover the envelope and admin gating. The `app` fixture keeps
an app context open for the duration of each test, so query functions can be
called directly.
"""
from datetime import datetime, timedelta

import pytest

from app.models import (
    db, AiUsage,
    BBChatConversation, BBChatMessage, BBDrawingReview,
    ReleasePhoto, BoardActivity, ReleaseEvents,
)
from app.brain.metrics import queries
from app.brain.metrics.timeframe import resolve_window
from app.services import ai_usage as ai_usage_service
from scripts.backfill_ai_usage import backfill
from tests.conftest import make_user

NOW = datetime.utcnow
WEEK = None  # resolved per-test via resolve_window("week")


def _window():
    _, start, end = resolve_window("week")
    return start, end


def _seed_photo(user, *, deleted=False, when=None):
    db.session.add(ReleasePhoto(
        release_id=1, storage_key="k", file_size_bytes=10,
        uploaded_by_user_id=user.id, is_deleted=deleted,
        uploaded_at=when or NOW(),
    ))


def _seed_event(action, *, user, echo=False, hash_="h", when=None):
    db.session.add(ReleaseEvents(
        job=100, release="1", action=action, payload={}, payload_hash=hash_,
        source="Brain", internal_user_id=user.id, is_system_echo=echo,
        created_at=when or NOW(),
    ))


# ---------------------------------------------------------------------------
# AI usage — now reads the unified ai_usage ledger
# ---------------------------------------------------------------------------

def _seed_usage(*, feature, user_id=None, model="claude-sonnet-5", cost=1.0,
                inp=100, out=50, dur=None, when=None, entity_type=None, entity_id=None):
    db.session.add(AiUsage(
        feature=feature, user_id=user_id, model=model,
        input_tokens=inp, output_tokens=out, cost_usd=cost, duration_ms=dur,
        entity_type=entity_type, entity_id=entity_id, created_at=when or NOW(),
    ))


def test_ai_usage_aggregates_ledger(app):
    u = make_user("alice", first_name="Alice", last_name="A")
    _seed_usage(feature="bb_chat", user_id=u.id, cost=0.5, inp=100, out=200, dur=1200)
    _seed_usage(feature="pdf_review", user_id=u.id, model="claude-opus-4-8", cost=30.0,
                inp=1_000_000, out=1_000_000)
    db.session.commit()

    start, end = _window()
    result = queries.ai_usage(start, end)

    assert result["totals"]["calls"] == 2
    assert result["totals"]["cost_usd"] == pytest.approx(30.5)
    assert {r["feature"] for r in result["by_feature"]} == {"bb_chat", "pdf_review"}
    assert result["by_user"][0]["username"] == "Alice A"
    assert result["totals"]["avg_duration_ms"] == 1200
    assert len(result["by_day"]) >= 1


def test_ai_usage_excludes_out_of_window(app):
    _seed_usage(feature="bb_chat", cost=9.0, when=NOW() - timedelta(days=40))
    db.session.commit()
    start, end = _window()
    assert queries.ai_usage(start, end)["totals"]["calls"] == 0


# ---------------------------------------------------------------------------
# Writer (app/services/ai_usage.record)
# ---------------------------------------------------------------------------

def test_record_computes_cost_when_not_given(app):
    # Opus-tier: 1M in * $5 + 1M out * $25 = $30.00.
    row = ai_usage_service.record(
        "pdf_review", model="claude-opus-4-8",
        input_tokens=1_000_000, output_tokens=1_000_000,
        entity_type="drawing_review", entity_id=7,
    )
    assert row is not None
    assert row.cost_usd == pytest.approx(30.0)
    assert row.entity_id == "7"  # coerced to string
    assert AiUsage.query.count() == 1


def test_record_uses_supplied_cost(app):
    row = ai_usage_service.record("bb_chat", model="claude-sonnet-5",
                                  input_tokens=10, output_tokens=10, cost_usd=0.123)
    assert row.cost_usd == pytest.approx(0.123)


# ---------------------------------------------------------------------------
# Backfill (scripts/backfill_ai_usage)
# ---------------------------------------------------------------------------

def test_backfill_from_sources_and_dedup(app):
    u = make_user("carol")
    conv = BBChatConversation(user_id=u.id)
    db.session.add(conv)
    db.session.flush()
    db.session.add(BBChatMessage(
        conversation_id=conv.id, role="assistant", content="hi",
        model="claude-sonnet-5", input_tokens=100, output_tokens=200, cost_usd=0.5,
        created_at=NOW(),
    ))
    db.session.add(BBDrawingReview(
        drawing_version_id=1, release_id=1, status="complete",
        model="claude-opus-4-8", input_tokens=1_000_000, output_tokens=1_000_000,
        requested_by_user_id=u.id, created_at=NOW(),
    ))
    db.session.commit()

    written = backfill(db.session, apply=True)
    assert written == 2
    assert AiUsage.query.count() == 2
    # pdf_review cost computed during backfill from tokens.
    pdf = AiUsage.query.filter_by(feature="pdf_review").first()
    assert pdf.cost_usd == pytest.approx(30.0)

    # Re-run is idempotent — dedup on (feature, entity_type, entity_id).
    assert backfill(db.session, apply=True) == 0
    assert AiUsage.query.count() == 2


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

def test_content_excludes_deleted_photos(app):
    u = make_user("carol")
    _seed_photo(u)
    _seed_photo(u, deleted=True)
    db.session.add(BoardActivity(
        item_id=1, type="comment", body="hey", author_id=u.id, author_name="Carol",
        created_at=NOW()))
    db.session.add(BoardActivity(
        item_id=1, type="status_change", old_value="open", new_value="closed",
        author_id=u.id, author_name="Carol", created_at=NOW()))
    db.session.commit()

    start, end = _window()
    result = queries.content(start, end)
    assert result["totals"]["release_photos"] == 1        # deleted one excluded
    assert result["totals"]["board_comments"] == 1        # status_change not counted
    assert len(result["by_type"]["release_photos"]["by_day"]) >= 1


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

def test_activity_excludes_system_echoes(app):
    u = make_user("dave")
    _seed_event("update_stage", user=u, hash_="a")
    _seed_event("update_stage", user=u, echo=True, hash_="b")   # echo → excluded
    _seed_event("update_fab_order", user=u, hash_="c")
    db.session.commit()

    start, end = _window()
    result = queries.activity(start, end)
    assert result["total"] == 2
    actions = {r["action"]: r["count"] for r in result["by_action"]}
    assert actions == {"update_stage": 1, "update_fab_order": 1}


# ---------------------------------------------------------------------------
# Summary + digest
# ---------------------------------------------------------------------------

def test_summary_and_digest_text(app):
    u = make_user("erin")
    _seed_photo(u)
    _seed_event("update_stage", user=u, hash_="z")
    db.session.commit()

    _, start, end = resolve_window("week")
    s = queries.summary(start, end)
    assert s["content"]["photos"] == 1
    assert s["activity"]["human_actions"] == 1
    text = queries.digest_text("week", s)
    assert "This week:" in text and "1 photos" in text


# ---------------------------------------------------------------------------
# HTTP: envelope + admin gating
# ---------------------------------------------------------------------------

def test_summary_endpoint_returns_envelope(admin_client):
    resp = admin_client.get("/brain/metrics/summary?period=week")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["period"] == "week"
    assert {"ai", "content", "activity", "system"} <= set(body)


def test_metrics_requires_admin(non_admin_client):
    assert non_admin_client.get("/brain/metrics/summary").status_code == 403
