"""Tests for app/services/outbox_service.py."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import ReleaseEvents, TrelloOutbox, db
from app.services.outbox_service import OutboxService

from tests.conftest import make_release


def _make_event(*, action="update_stage", to_value="Paint Start", job=1, release="A"):
    ev = ReleaseEvents(
        job=job, release=release,
        action=action,
        payload={"to": to_value},
        payload_hash=f"hash-{job}-{release}-{action}-{to_value}",
        source="Brain",
    )
    db.session.add(ev)
    db.session.flush()
    return ev


def _add_move_card_item(event_id):
    item = OutboxService.add(destination="trello", action="move_card", event_id=event_id)
    db.session.commit()
    return item


@contextmanager
def _trello_move_patches(side_effect=None):
    """Patch the two lazy imports the move_card path makes into Trello."""
    api_kwargs = {"side_effect": side_effect} if side_effect else {}
    with patch("app.trello.api.update_trello_card", **api_kwargs) as mock_api, \
         patch("app.brain.job_log.routes.get_list_id_by_stage", return_value="list-xyz"):
        yield mock_api


def test_add_creates_pending_outbox_item(app):
    with app.app_context():
        ev = _make_event()
        item = _add_move_card_item(ev.id)

        fetched = db.session.get(TrelloOutbox, item.id)
        assert fetched.destination == "trello"
        assert fetched.action == "move_card"
        assert fetched.status == "pending"
        assert fetched.retry_count == 0
        assert fetched.event_id == ev.id


def test_process_item_move_card_success(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-123")
        item = _add_move_card_item(_make_event().id)

        with _trello_move_patches() as mock_api:
            assert OutboxService.process_item(item) is True

        db.session.refresh(item)
        assert item.status == "completed"
        assert item.error_message is None
        assert item.completed_at is not None
        mock_api.assert_called_once_with("card-123", new_list_id="list-xyz")


def test_process_item_failure_increments_retry_with_backoff(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-123")
        item = _add_move_card_item(_make_event().id)

        with _trello_move_patches(side_effect=Exception("boom")):
            assert OutboxService.process_item(item) is False

        db.session.refresh(item)
        assert item.status == "pending"
        assert item.retry_count == 1
        assert item.error_message == "boom"
        assert item.next_retry_at > datetime.utcnow() + timedelta(seconds=1)


def test_process_item_exhausts_retries_and_marks_failed(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-123")
        item = _add_move_card_item(_make_event().id)
        item.retry_count = item.max_retries - 1
        db.session.commit()

        with _trello_move_patches(side_effect=Exception("still broken")):
            OutboxService.process_item(item)

        db.session.refresh(item)
        assert item.status == "failed"
        assert item.retry_count == item.max_retries


def test_process_item_unsupported_action_marks_failed(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-123")
        item = OutboxService.add(
            destination="trello", action="conjure_card", event_id=_make_event().id,
        )
        db.session.commit()

        OutboxService.process_item(item)

        db.session.refresh(item)
        assert item.status == "failed"
        assert "Unsupported" in (item.error_message or "")


def test_process_item_no_associated_release_marks_failed(app):
    with app.app_context():
        # No make_release — process_item must fail to derive card_id
        item = _add_move_card_item(_make_event().id)

        OutboxService.process_item(item)

        db.session.refresh(item)
        assert item.status == "failed"
        assert "not found" in (item.error_message or "").lower()


def test_process_item_missing_card_id_marks_failed(app):
    with app.app_context():
        make_release(1, "A", trello_card_id=None)
        item = _add_move_card_item(_make_event().id)

        OutboxService.process_item(item)

        db.session.refresh(item)
        assert item.status == "failed"


def test_process_pending_items_returns_zero_when_empty(app):
    with app.app_context():
        assert OutboxService.process_pending_items(limit=10) == 0


def test_process_pending_items_respects_limit(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-123")
        for i in range(3):
            _add_move_card_item(_make_event(action=f"update_stage_{i}").id)

        with _trello_move_patches() as mock_api:
            assert OutboxService.process_pending_items(limit=2) == 2
        assert mock_api.call_count == 2


def test_process_pending_items_skips_future_retry(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-123")
        item = _add_move_card_item(_make_event().id)
        item.next_retry_at = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()

        with _trello_move_patches() as mock_api:
            assert OutboxService.process_pending_items(limit=10) == 0
        mock_api.assert_not_called()
