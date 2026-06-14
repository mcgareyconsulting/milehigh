"""Tests for calendar → Recall scheduling.

Graph (calendarView) and Recall dispatch are both patched so tests are hermetic —
no live Graph token, no live Recall call.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.brain.meetings import calendar, recall
from app.models import db, Meeting


def _graph_dt(dt):
    """Render a naive-UTC datetime the way Graph returns it under outlook.timezone=UTC."""
    return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"}


def _event(event_id, *, start, subject="Shop touch-base", join_url="https://teams.microsoft.com/l/meetup-join/abc"):
    ev = {
        "id": event_id,
        "subject": subject,
        "start": _graph_dt(start),
        "end": _graph_dt(start + timedelta(minutes=30)),
        "isOnlineMeeting": bool(join_url),
        "bodyPreview": "agenda: discuss 480-146",
    }
    ev["onlineMeeting"] = {"joinUrl": join_url} if join_url else None
    return ev


# --------------------------------------------------------------------------- #
# recall.dispatch_bot join_at
# --------------------------------------------------------------------------- #
def test_dispatch_bot_includes_join_at_when_scheduled(app):
    join_at = datetime(2026, 6, 12, 18, 30, 0)
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "bot-123"}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["body"] = json
        return _Resp()

    with patch.object(recall, "cfg") as mcfg, patch.object(recall.requests, "post", _fake_post):
        mcfg.RECALL_API_KEY = "k"
        mcfg.RECALL_BASE_URL = "https://x.recall.ai/api/v1"
        bot_id = recall.dispatch_bot("https://teams.microsoft.com/x", join_at=join_at)

    assert bot_id == "bot-123"
    assert captured["body"]["join_at"] == "2026-06-12T18:30:00Z"


def test_dispatch_bot_omits_join_at_for_immediate(app):
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "bot-9"}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["body"] = json
        return _Resp()

    with patch.object(recall, "cfg") as mcfg, patch.object(recall.requests, "post", _fake_post):
        mcfg.RECALL_API_KEY = "k"
        mcfg.RECALL_BASE_URL = "https://x.recall.ai/api/v1"
        recall.dispatch_bot("https://teams.microsoft.com/x")

    assert "join_at" not in captured["body"]


# --------------------------------------------------------------------------- #
# calendar.poll()
# --------------------------------------------------------------------------- #
def test_poll_schedules_bot_for_upcoming_teams_meeting(app):
    start = datetime.utcnow() + timedelta(minutes=30)
    events = [_event("evt-1", start=start, subject="GC sync")]

    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": events}), \
            patch.object(recall, "dispatch_bot", return_value="bot-1") as mdispatch:
        result = calendar.poll()

        assert result["scheduled"] == 1
        # dispatched with a future join_at (start minus the lead).
        _, kwargs = mdispatch.call_args
        assert kwargs["join_at"] is not None and kwargs["join_at"] < start

        meeting = Meeting.query.filter_by(calendar_event_id="evt-1").first()
        assert meeting is not None
        assert meeting.source == "recall"
        assert meeting.bot_status == "scheduled"
        assert meeting.recall_bot_id == "bot-1"
        assert meeting.title == "GC sync"
        assert meeting.occurred_at == start.replace(microsecond=0)


def test_poll_is_idempotent_across_runs(app):
    start = datetime.utcnow() + timedelta(minutes=20)
    events = [_event("evt-dupe", start=start)]

    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": events}), \
            patch.object(recall, "dispatch_bot", return_value="bot-x") as mdispatch:
        first = calendar.poll()
        second = calendar.poll()

    assert first["scheduled"] == 1
    assert second["scheduled"] == 0 and second["skipped"] == 1
    assert mdispatch.call_count == 1
    assert Meeting.query.filter_by(calendar_event_id="evt-dupe").count() == 1


def test_poll_skips_non_teams_events(app):
    start = datetime.utcnow() + timedelta(minutes=15)
    events = [_event("evt-no-link", start=start, join_url=None)]

    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": events}), \
            patch.object(recall, "dispatch_bot") as mdispatch:
        result = calendar.poll()

    assert result["scheduled"] == 0 and result["skipped"] == 1
    mdispatch.assert_not_called()
    assert Meeting.query.count() == 0


def test_poll_joins_in_progress_meeting_immediately(app):
    # Event already started (inside the calendarView window) → join now (join_at=None).
    start = datetime.utcnow() - timedelta(minutes=5)
    events = [_event("evt-live", start=start)]

    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": events}), \
            patch.object(recall, "dispatch_bot", return_value="bot-live") as mdispatch:
        calendar.poll()
        _, kwargs = mdispatch.call_args
        assert kwargs["join_at"] is None


def test_parse_graph_dt_trims_to_naive_utc():
    parsed = calendar._parse_graph_dt({"dateTime": "2026-06-12T18:30:00.0000000", "timeZone": "UTC"})
    assert parsed == datetime(2026, 6, 12, 18, 30, 0)
    assert calendar._parse_graph_dt(None) is None
    assert calendar._parse_graph_dt({"dateTime": "garbage"}) is None


# --------------------------------------------------------------------------- #
# join-URL extraction (structured → onlineMeetingUrl → body link)
# --------------------------------------------------------------------------- #
def test_join_url_falls_back_to_online_meeting_url_then_body():
    assert calendar._join_url({"onlineMeeting": {"joinUrl": " https://teams.microsoft.com/l/a "}}) \
        == "https://teams.microsoft.com/l/a"
    assert calendar._join_url(
        {"onlineMeeting": None, "onlineMeetingUrl": "https://teams.microsoft.com/l/b"}
    ) == "https://teams.microsoft.com/l/b"
    assert calendar._join_url(
        {"bodyPreview": "join here https://teams.microsoft.com/l/meetup-join/xyz now"}
    ) == "https://teams.microsoft.com/l/meetup-join/xyz"
    assert calendar._join_url({"bodyPreview": "no link here"}) is None


# --------------------------------------------------------------------------- #
# reconciliation: cancel / reschedule / dry-run
# --------------------------------------------------------------------------- #
def test_poll_cancels_bot_when_event_cancelled(app):
    start = datetime.utcnow() + timedelta(minutes=40)
    live = [_event("evt-c", start=start)]
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": live}), \
            patch.object(recall, "dispatch_bot", return_value="bot-c"):
        calendar.poll()

    cancelled_event = _event("evt-c", start=start)
    cancelled_event["isCancelled"] = True
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": [cancelled_event]}), \
            patch.object(recall, "delete_bot", return_value=True) as mdelete:
        result = calendar.poll()

    assert result["cancelled"] == 1
    mdelete.assert_called_once_with("bot-c")
    meeting = Meeting.query.filter_by(calendar_event_id="evt-c").first()
    assert meeting.bot_status == "cancelled"


def test_poll_reschedules_bot_when_start_moves(app):
    start = datetime.utcnow() + timedelta(minutes=40)
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": [_event("evt-m", start=start)]}), \
            patch.object(recall, "dispatch_bot", return_value="bot-old"):
        calendar.poll()

    moved = start + timedelta(hours=2)  # outside the first window, but reconciled by id
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": [_event("evt-m", start=moved)]}), \
            patch.object(recall, "delete_bot", return_value=True) as mdelete, \
            patch.object(recall, "dispatch_bot", return_value="bot-new") as mdispatch:
        result = calendar.poll()

    assert result["rescheduled"] == 1
    mdelete.assert_called_once_with("bot-old")
    assert mdispatch.call_count == 1
    meeting = Meeting.query.filter_by(calendar_event_id="evt-m").first()
    assert meeting.recall_bot_id == "bot-new"
    assert meeting.occurred_at == moved.replace(microsecond=0)


def test_poll_skips_reschedule_when_bot_already_joining(app):
    start = datetime.utcnow() + timedelta(minutes=40)
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": [_event("evt-j", start=start)]}), \
            patch.object(recall, "dispatch_bot", return_value="bot-j"):
        calendar.poll()
        # Bot has gone live — reconciliation must leave it alone.
        Meeting.query.filter_by(calendar_event_id="evt-j").first().bot_status = "in_call_recording"
        db.session.commit()

    moved = start + timedelta(minutes=15)
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": [_event("evt-j", start=moved)]}), \
            patch.object(recall, "delete_bot") as mdelete, \
            patch.object(recall, "dispatch_bot") as mdispatch:
        result = calendar.poll()

    assert result["skipped"] == 1
    mdelete.assert_not_called()
    mdispatch.assert_not_called()


def test_poll_skips_declined_event(app):
    start = datetime.utcnow() + timedelta(minutes=30)
    ev = _event("evt-d", start=start)
    ev["responseStatus"] = {"response": "declined"}
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": [ev]}), \
            patch.object(recall, "dispatch_bot") as mdispatch:
        result = calendar.poll()
    assert result["scheduled"] == 0 and result["skipped"] == 1
    mdispatch.assert_not_called()
    assert Meeting.query.count() == 0


def test_dry_run_classifies_without_dispatching(app):
    start = datetime.utcnow() + timedelta(minutes=30)
    with app.app_context(), \
            patch.object(calendar, "graph_get", return_value={"value": [_event("evt-dry", start=start)]}), \
            patch.object(recall, "dispatch_bot") as mdispatch:
        result = calendar.poll(dry_run=True)

    assert result["scheduled"] == 1 and result["dry_run"] is True
    mdispatch.assert_not_called()
    assert Meeting.query.count() == 0  # nothing persisted


# --------------------------------------------------------------------------- #
# on-demand admin endpoint
# --------------------------------------------------------------------------- #
def test_trigger_endpoint_503_when_disabled(admin_client):
    resp = admin_client.post('/brain/meetings/calendar/poll', json={})
    assert resp.status_code == 503


def test_trigger_endpoint_runs_poll_when_enabled(admin_client, app):
    app.config['RECALL_CALENDAR_ENABLED'] = True
    start = datetime.utcnow() + timedelta(minutes=30)
    with patch.object(calendar, "graph_get", return_value={"value": [_event("evt-ep", start=start)]}), \
            patch.object(recall, "dispatch_bot", return_value="bot-ep"):
        resp = admin_client.post('/brain/meetings/calendar/poll', json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok" and body["scheduled"] == 1
