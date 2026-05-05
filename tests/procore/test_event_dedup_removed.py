"""
Verify that content-based payload_hash dedup has been removed from
create_submittal_event. Two SubmittalEvents rows with identical payload_hash
must both be persisted; burst dedup is the receipt-layer's job, not the
event-layer's.

See docs/procore-webhook-plan.md Phase 1.1.
"""
import pytest

from app import create_app
from app.models import db, SubmittalEvents


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


class TestEventDedupRemoved:
    def test_identical_payload_hash_inserts_both_succeed(self, app):
        from app.procore.helpers import create_submittal_event

        payload = {"status": {"old": "Open", "new": "Closed"}}

        first = create_submittal_event("123", "updated", payload, source="Procore")
        second = create_submittal_event("123", "updated", payload, source="Procore")

        assert first is True
        assert second is True

        rows = SubmittalEvents.query.filter_by(submittal_id="123").all()
        assert len(rows) == 2
        assert rows[0].payload_hash == rows[1].payload_hash

    def test_empty_payload_for_update_still_skipped(self, app):
        from app.procore.helpers import create_submittal_event

        result = create_submittal_event("456", "updated", {}, source="Procore")
        assert result is False
        assert SubmittalEvents.query.filter_by(submittal_id="456").count() == 0
