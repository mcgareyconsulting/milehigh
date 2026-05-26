"""Tests for RecordPickupCommand and the create_pickup_card outbox branch."""
from datetime import datetime

import pytest

from app.models import Releases, PickupOrder, ReleaseEvents, TrelloOutbox, db


def make_release(job, release, job_name="Test Job"):
    r = Releases(job=job, release=release, job_name=job_name, stage="Released")
    db.session.add(r)
    db.session.flush()
    return r


def run_command(**overrides):
    from app.brain.job_log.features.pickup.command import RecordPickupCommand
    kwargs = dict(
        job_id=123,
        release="V4",
        vendor="Dencol",
        email_message_id="msg-abc",
        email_subject="123-V4 parts ready",
        email_from="vendor@dencol.com",
        email_to="pu@example.com",
        email_body="Full forwarded traceback...",
        email_received_at=datetime(2026, 5, 26, 9, 0, 0),
    )
    kwargs.update(overrides)
    return RecordPickupCommand(**kwargs).execute()


def test_records_pickup_with_event_and_outbox(app):
    with app.app_context():
        rel = make_release(123, "V4")
        db.session.commit()

        result = run_command()

        pickup = PickupOrder.query.filter_by(email_message_id="msg-abc").first()
        assert pickup is not None
        assert pickup.release_id == rel.id
        assert pickup.job == 123 and pickup.release == "V4"
        assert pickup.vendor == "Dencol"
        assert pickup.status == "received"
        assert pickup.email_body == "Full forwarded traceback..."
        assert result.pickup_order_id == pickup.id
        assert result.deduplicated is False

        event = ReleaseEvents.query.filter_by(action="pickup_received", job=123).first()
        assert event is not None
        assert event.payload["pickup_order_id"] == pickup.id
        assert event.source == "Email"

        outbox = TrelloOutbox.query.filter_by(action="create_pickup_card", event_id=event.id).first()
        assert outbox is not None
        assert outbox.status == "pending"


def test_idempotent_on_message_id(app):
    with app.app_context():
        make_release(123, "V4")
        db.session.commit()

        first = run_command()
        second = run_command()  # same email_message_id

        assert second.deduplicated is True
        assert second.pickup_order_id == first.pickup_order_id
        assert PickupOrder.query.filter_by(email_message_id="msg-abc").count() == 1


def test_missing_release_raises(app):
    with app.app_context():
        with pytest.raises(ValueError):
            run_command(job_id=999, release="Z9", email_message_id="msg-z")


def test_outbox_creates_pickup_card_under_trello_mock(app):
    with app.app_context():
        app.config["TRELLO_MOCK"] = True
        make_release(123, "V4")
        db.session.commit()

        result = run_command()
        outbox = TrelloOutbox.query.filter_by(action="create_pickup_card").first()

        from app.services.outbox_service import OutboxService
        ok = OutboxService.process_item(outbox)
        assert ok is True

        pickup = db.session.get(PickupOrder, result.pickup_order_id)
        assert pickup.status == "card_created"
        assert pickup.trello_card_id == f"MOCK_PU_{pickup.id}"
        assert pickup.trello_list_name == app.config["PICKUP_TRELLO_LIST_NAME"]

        db.session.refresh(outbox)
        assert outbox.status == "completed"
