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
