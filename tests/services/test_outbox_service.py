"""Tests for app/services/outbox_service.py."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
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


def test_trello_mock_move_card_writes_list_fields_and_skips_api(app):
    """With TRELLO_MOCK=True, process_item should NOT hit Trello's API and
    should mirror the move onto the Releases row + close the event."""
    with app.app_context():
        r = make_release(
            1, "A",
            trello_card_id="card-123",
            trello_list_id="old-list",
            trello_list_name="Paint start",
            stage="Paint Start",
        )
        ev = _make_event(to_value="Ship Planning")
        item = _add_move_card_item(ev.id)

        app.config["TRELLO_MOCK"] = True
        try:
            with patch("app.trello.api.update_trello_card") as mock_api:
                assert OutboxService.process_item(item) is True
            mock_api.assert_not_called()
        finally:
            app.config["TRELLO_MOCK"] = False

        db.session.refresh(item)
        db.session.refresh(r)
        db.session.refresh(ev)
        assert item.status == "completed"
        assert item.error_message is None
        assert r.trello_list_name == "Shipping planning"
        assert r.trello_list_id and r.trello_list_id.startswith("mock-")
        assert ev.applied_at is not None


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


# ---------------------------------------------------------------------------
# create_card idempotency on retry
# ---------------------------------------------------------------------------

def _add_create_card_item(event_id, retry_count=0):
    item = OutboxService.add(destination="trello", action="create_card", event_id=event_id)
    item.retry_count = retry_count
    db.session.commit()
    return item


def test_create_card_first_attempt_does_not_request_idempotency(app):
    """First attempt (retry_count=0) must NOT trigger the list-scan — avoids
    an extra GET on the hot path for normal card creations."""
    with app.app_context():
        make_release(1, "A", trello_card_id=None)
        ev = _make_event(action="created")
        item = _add_create_card_item(ev.id, retry_count=0)

        fresh = {
            "success": True,
            "adopted": False,
            "card_id": "fresh-1",
            "card_data": {"id": "fresh-1", "name": "x", "url": "u"},
        }
        with patch(
            "app.brain.job_log.routes.create_trello_card_for_job",
            return_value=fresh,
        ) as mock_create:
            assert OutboxService.process_item(item) is True

        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs.get("idempotency_check") is False

        db.session.refresh(item)
        assert item.status == "completed"


def test_create_card_retry_passes_idempotency_check_true(app):
    """retry_count>=1 must set idempotency_check=True so the wrapper scans
    the target list before re-POSTing."""
    with app.app_context():
        make_release(1, "A", trello_card_id=None)
        ev = _make_event(action="created")
        item = _add_create_card_item(ev.id, retry_count=2)

        adopted = {
            "success": True,
            "adopted": True,
            "card_id": "adopted-9",
            "card_data": {"id": "adopted-9", "name": "x", "url": "u"},
        }
        with patch(
            "app.brain.job_log.routes.create_trello_card_for_job",
            return_value=adopted,
        ) as mock_create:
            assert OutboxService.process_item(item) is True

        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs.get("idempotency_check") is True

        db.session.refresh(item)
        assert item.status == "completed"
        assert item.error_message is None


# ---------------------------------------------------------------------------
# update_release_fields (Job Log "Edit row" -> Trello sync)
# ---------------------------------------------------------------------------

def _make_fields_event(payload, job=1, release="A"):
    ev = ReleaseEvents(
        job=job, release=release,
        action="updated",
        payload=payload,
        payload_hash=f"hash-{job}-{release}-updated-{sorted(payload.keys())}",
        source="Brain",
    )
    db.session.add(ev)
    db.session.flush()
    return ev


def _add_update_release_fields_item(event_id):
    item = OutboxService.add(destination="trello", action="update_release_fields", event_id=event_id)
    db.session.commit()
    return item


def test_update_release_fields_regenerates_title_and_description(app):
    with app.app_context():
        make_release(
            1, "A",
            trello_card_id="card-555", mirror_trello_card_id="mirror-555",
            job_name="Acme Tower", description="Stair Core",
            install_hrs=10, paint_color="Black", pm="Bill", by="Dan",
            released=date(2026, 6, 1), num_guys=2,
        )
        ev = _make_fields_event({
            "pm": {"old_value": "Old PM", "new_value": "Bill"},
            "job_name": {"old_value": "Old Name", "new_value": "Acme Tower"},
        })
        item = _add_update_release_fields_item(ev.id)

        with patch("app.trello.api.update_trello_card_name") as mock_name, \
             patch("app.trello.api.update_trello_card_description") as mock_desc:
            assert OutboxService.process_item(item) is True

        # Pushed to the primary card...
        assert mock_name.call_args_list[0].args == ("card-555", "1-A Acme Tower Stair Core")
        assert mock_desc.call_args_list[0].args[0] == "card-555"
        assert "**Team:** PM: Bill / BY: Dan" in mock_desc.call_args_list[0].args[1]

        # ...and mirrored onto the linked mirror card with the same content.
        assert mock_name.call_args_list[1].args == ("mirror-555", "1-A Acme Tower Stair Core")
        assert mock_desc.call_args_list[1].args[0] == "mirror-555"
        assert mock_desc.call_args_list[1].args[1] == mock_desc.call_args_list[0].args[1]

        db.session.refresh(item)
        db.session.refresh(ev)
        assert item.status == "completed"
        assert ev.applied_at is not None


def test_update_release_fields_skips_trello_when_only_fab_hrs_changed(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-555")
        ev = _make_fields_event({"fab_hrs": {"old_value": 10, "new_value": 12}})
        item = _add_update_release_fields_item(ev.id)

        with patch("app.trello.api.update_trello_card_name") as mock_name, \
             patch("app.trello.api.update_trello_card_description") as mock_desc:
            assert OutboxService.process_item(item) is True

        mock_name.assert_not_called()
        mock_desc.assert_not_called()

        db.session.refresh(item)
        db.session.refresh(ev)
        assert item.status == "completed"
        assert ev.applied_at is not None


def test_update_release_fields_missing_card_id_marks_failed(app):
    with app.app_context():
        make_release(1, "A", trello_card_id=None)
        ev = _make_fields_event({"pm": {"old_value": "Old", "new_value": "New"}})
        item = _add_update_release_fields_item(ev.id)

        assert OutboxService.process_item(item) is False

        db.session.refresh(item)
        assert item.status == "failed"


def test_update_release_fields_retries_on_failure(app):
    with app.app_context():
        make_release(1, "A", trello_card_id="card-555", pm="Old PM")
        ev = _make_fields_event({"pm": {"old_value": "Old PM", "new_value": "New PM"}})
        item = _add_update_release_fields_item(ev.id)

        with patch("app.trello.api.update_trello_card_description", side_effect=Exception("boom")):
            assert OutboxService.process_item(item) is False

        db.session.refresh(item)
        assert item.status == "pending"
        assert item.retry_count == 1
        assert item.error_message == "boom"


def test_update_release_fields_mirror_failure_is_best_effort(app):
    """A mirror-card push failure must not fail the outbox item — the primary
    card already synced successfully, and the mirror is best-effort."""
    with app.app_context():
        make_release(1, "A", trello_card_id="card-555", mirror_trello_card_id="mirror-555", pm="Old PM")
        ev = _make_fields_event({"pm": {"old_value": "Old PM", "new_value": "New PM"}})
        item = _add_update_release_fields_item(ev.id)

        with patch("app.trello.api.update_trello_card_description") as mock_desc:
            mock_desc.side_effect = [None, Exception("mirror unreachable")]
            assert OutboxService.process_item(item) is True

        assert mock_desc.call_count == 2
        db.session.refresh(item)
        db.session.refresh(ev)
        assert item.status == "completed"
        assert ev.applied_at is not None


def test_create_card_retry_failure_does_not_double_invoke(app):
    """If the retry still fails, the outbox increments retry_count and stays
    pending — sanity-check that the contract didn't regress."""
    with app.app_context():
        make_release(1, "A", trello_card_id=None)
        ev = _make_event(action="created")
        item = _add_create_card_item(ev.id, retry_count=1)

        with patch(
            "app.brain.job_log.routes.create_trello_card_for_job",
            return_value={"success": False, "error": "still 500"},
        ) as mock_create:
            assert OutboxService.process_item(item) is False

        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs.get("idempotency_check") is True

        db.session.refresh(item)
        assert item.retry_count == 2
        assert item.status == "pending"
        assert "still 500" in (item.error_message or "")
