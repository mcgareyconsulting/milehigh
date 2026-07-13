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
    BBChatConversation, BBChatMessage, BBDrawingReview, BBReviewFeedback,
    ReleasePhoto, BoardActivity, ReleaseEvents,
    Meeting, ChecklistItem, Notification, TrelloOutbox,
    SyncOperation, SyncStatus, WebhookReceipt,
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
# Engagement (item 1)
# ---------------------------------------------------------------------------

def test_engagement_active_users_and_logins(app):
    u1 = make_user("frank", first_name="Frank")
    u2 = make_user("gina", first_name="Gina")
    u1.last_login = NOW()
    u2.last_login = NOW() - timedelta(days=40)  # logged in long ago (not in window)
    _seed_event("update_stage", user=u1, hash_="e1")     # u1 active via events
    _seed_photo(u2)                                       # u2 active via upload
    db.session.commit()

    start, end = _window()
    r = queries.engagement(start, end)
    assert r["active_users"] == 2                 # both took some action
    assert r["logins_in_window"] == 1             # only u1 logged in within the window
    top = next(x for x in r["roster"] if x["user_id"] == u1.id)
    assert top["actions"] == 1


# ---------------------------------------------------------------------------
# Quality (item 3)
# ---------------------------------------------------------------------------

def test_quality_accept_rates(app):
    # 3 accepted + 1 rejected finding -> 0.75
    for i, dec in enumerate(["accepted", "accepted", "accepted", "rejected"]):
        db.session.add(BBReviewFeedback(
            review_id=1, release_id=1, finding_index=i, decision=dec, created_at=NOW()))
    m = Meeting(title="m")
    db.session.add(m)
    db.session.flush()
    db.session.add(ChecklistItem(meeting_id=m.id, title="todo A", status="accepted", reviewed_at=NOW()))
    db.session.add(ChecklistItem(meeting_id=m.id, title="todo B", status="rejected", reviewed_at=NOW()))
    db.session.commit()

    start, end = _window()
    q = queries.quality(start, end)
    assert q["bb_review_findings"]["accept_rate"] == pytest.approx(0.75)
    assert q["meeting_todos"]["accept_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Throughput / cycle time (item 8)
# ---------------------------------------------------------------------------

def test_throughput_created_completed_and_dwell(app):
    u = make_user("hank")
    _seed_event("created", user=u, hash_="c1")
    # Two stage changes for the same release: Cut Start (t0) then Complete 2 days later.
    t0 = NOW() - timedelta(days=3)
    db.session.add(ReleaseEvents(
        job=100, release="1", action="update_stage", payload={"from": "X", "to": "Cut Start"},
        payload_hash="s1", source="Brain", internal_user_id=u.id, created_at=t0))
    db.session.add(ReleaseEvents(
        job=100, release="1", action="update_stage", payload={"from": "Cut Start", "to": "Complete"},
        payload_hash="s2", source="Brain", internal_user_id=u.id, created_at=t0 + timedelta(days=2)))
    db.session.commit()

    start, end = _window()
    tp = queries.throughput(start, end)
    assert tp["releases_created"] == 1
    assert tp["releases_completed"] == 1            # reached the complete zone
    dwell = {d["stage"]: d["avg_days"] for d in tp["stage_dwell_days"]}
    assert dwell["Cut Start"] == pytest.approx(2.0)  # 2 days between the two stage events


# ---------------------------------------------------------------------------
# AI reliability + latency (items 2 + 9)
# ---------------------------------------------------------------------------

def test_ai_reliability_status_and_latency(app):
    # One complete review (120s latency), one errored.
    db.session.add(BBDrawingReview(
        drawing_version_id=1, release_id=1, status="complete", model="claude-opus-4-8",
        created_at=NOW() - timedelta(seconds=120), completed_at=NOW()))
    db.session.add(BBDrawingReview(
        drawing_version_id=1, release_id=1, status="error", created_at=NOW()))
    db.session.commit()

    start, end = _window()
    r = queries.ai_reliability(start, end)
    assert r["reviews"]["complete"] == 1 and r["reviews"]["error"] == 1
    assert r["reviews"]["success_rate"] == pytest.approx(0.5)
    assert r["reviews"]["avg_latency_s"] == pytest.approx(120, abs=2)


# ---------------------------------------------------------------------------
# Content storage + mention read-rate (items 6 + 7)
# ---------------------------------------------------------------------------

def test_content_storage_and_mention_read_rate(app):
    u = make_user("iris")
    db.session.add(ReleasePhoto(release_id=1, storage_key="k", file_size_bytes=1000,
                                uploaded_by_user_id=u.id, uploaded_at=NOW()))
    db.session.add(Notification(user_id=u.id, type="mention", message="hi", is_read=True, created_at=NOW()))
    db.session.add(Notification(user_id=u.id, type="mention", message="yo", is_read=False, created_at=NOW()))
    db.session.commit()

    start, end = _window()
    c = queries.content(start, end)
    assert c["storage"]["added_bytes"]["release_photos"] == 1000
    assert c["storage"]["added_bytes"]["all"] == 1000
    assert c["mentions_read"]["read_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# System delivery reliability + freshness (items 4 + 5)
# ---------------------------------------------------------------------------

def test_system_delivery_and_freshness(app):
    db.session.add(TrelloOutbox(event_id=1, destination="trello", action="move_card",
                                status="completed", created_at=NOW()))
    db.session.add(TrelloOutbox(event_id=2, destination="trello", action="move_card",
                                status="failed", created_at=NOW()))
    db.session.add(SyncOperation(operation_id="op1", operation_type="trello_webhook",
                                 status=SyncStatus.COMPLETED, started_at=NOW() - timedelta(minutes=30),
                                 completed_at=NOW() - timedelta(minutes=30)))
    db.session.add(WebhookReceipt(receipt_hash="rh1", provider="procore", received_at=NOW() - timedelta(minutes=5)))
    db.session.commit()

    start, end = _window()
    sysm = queries.system(start, end)
    assert sysm["outbox_delivery"]["trello"]["success_rate"] == pytest.approx(0.5)
    assert sysm["outbox_delivery"]["trello"]["failed"] == 1
    assert sysm["freshness"]["last_sync_age_minutes"] == pytest.approx(30, abs=2)
    assert sysm["freshness"]["last_webhook_age_minutes"] == pytest.approx(5, abs=2)


# ---------------------------------------------------------------------------
# HTTP: envelope + admin gating
# ---------------------------------------------------------------------------

def test_summary_endpoint_returns_envelope(admin_client):
    resp = admin_client.get("/brain/metrics/summary?period=week")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["period"] == "week"
    assert {"ai", "content", "activity", "system", "engagement", "quality", "throughput"} <= set(body)


def test_new_endpoints_respond(admin_client):
    for path in ("engagement", "quality", "throughput", "ai"):
        assert admin_client.get(f"/brain/metrics/{path}?period=week").status_code == 200


def test_metrics_requires_admin(non_admin_client):
    assert non_admin_client.get("/brain/metrics/summary").status_code == 403
