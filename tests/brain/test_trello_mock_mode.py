"""TRELLO_MOCK — local dev must reach zero Trello network calls.

Mock mode used to simulate exactly one outbound action (move_card) while every other outbox action
and every direct card write went to the real board. These tests pin the invariant that matters for
local dev: with TRELLO_MOCK on, nothing outbound escapes, and the DB still ends up in the state a
successful round-trip would have produced.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.models import Releases, ReleaseEvents, TrelloOutbox, db
from app.services.outbox_service import OutboxService
from tests.conftest import make_release


@pytest.fixture(autouse=True)
def setup_auth(admin_session):
    yield


@pytest.fixture
def mock_mode(app):
    """Turn on TRELLO_MOCK for both lookup paths: app.config (outbox) and Config (trello.api)."""
    app.config["TRELLO_MOCK"] = True
    with patch("app.trello.api.cfg.TRELLO_MOCK", True):
        yield
    app.config["TRELLO_MOCK"] = False


@pytest.fixture
def no_network():
    """Any real HTTP call from the Trello client is a test failure."""
    with patch("app.trello.api.requests") as rq:
        rq.get.side_effect = AssertionError("Trello GET escaped TRELLO_MOCK")
        rq.put.side_effect = AssertionError("Trello PUT escaped TRELLO_MOCK")
        rq.post.side_effect = AssertionError("Trello POST escaped TRELLO_MOCK")
        yield


def _release(job, release, **kw):
    return make_release(job, release, **{
        "stage": "Paint Start",
        "start_install_formulaTF": True,
        "trello_card_id": "card-123",
        **kw,
    })


class TestMockModeMakesNoNetworkCalls:
    def test_assigning_an_installer_makes_no_call_and_still_syncs_state(
        self, app, admin_client, mock_mode, no_network
    ):
        with app.app_context():
            _release(1, "A", start_install=date(2026, 6, 15), start_install_formulaTF=False)
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A", json={"installer": "Saul 2"}
            )
            assert resp.status_code == 200

            processed = OutboxService.process_pending_items(limit=10)
            assert processed == 1

            db.session.expire_all()
            r = Releases.query.filter_by(job=1, release="A").first()
            assert r.installer == "Saul 2"
            # The mirror id the real path would have persisted is simulated, so downstream
            # reads that gate on it behave the same locally.
            assert r.mirror_trello_card_id == "mock-mirror-1-A"

            item = TrelloOutbox.query.filter_by(action="assign_installer").one()
            assert item.status == "completed"
            assert ReleaseEvents.query.filter_by(action="update_installer").one().applied_at is not None

    def test_a_full_timeline_drop_makes_no_call(self, app, admin_client, mock_mode, no_network):
        """Date + installer in one PATCH — the drag's exact shape. The date half pushes Trello
        directly (not via the outbox), so this is the case the old move_card-only mock missed."""
        with app.app_context():
            _release(1, "A")
            db.session.commit()

            with patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={"start_install": "2026-06-15", "installer": "Saul 2"},
                )
            assert resp.status_code == 200
            assert OutboxService.process_pending_items(limit=10) == 1

            db.session.expire_all()
            r = Releases.query.filter_by(job=1, release="A").first()
            assert r.start_install == date(2026, 6, 15)
            assert r.installer == "Saul 2"

    def test_a_stage_move_still_writes_the_target_list_locally(
        self, app, admin_client, mock_mode, no_network
    ):
        """The pre-existing move_card simulation must survive being generalised."""
        with app.app_context():
            _release(1, "A", stage="Paint Start")
            db.session.commit()

            with patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
                resp = admin_client.patch(
                    "/brain/update-stage/1/A", json={"stage": "Paint Complete"}
                )
            assert resp.status_code == 200

            OutboxService.process_pending_items(limit=10)
            db.session.expire_all()
            r = Releases.query.filter_by(job=1, release="A").first()
            assert r.stage == "Paint Complete"
            assert r.trello_list_name == "Paint complete"
            assert r.trello_list_id is not None

    def test_clearing_a_hard_date_makes_no_call(self, app, admin_client, mock_mode, no_network):
        """clear_hard_date pushes a due-date clear straight to Trello, outside the outbox."""
        with app.app_context():
            _release(1, "A", start_install=date(2026, 6, 15), start_install_formulaTF=False)
            db.session.commit()

            with patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A", json={"clear_hard_date": True}
                )
            assert resp.status_code == 200


class TestMockModeIsOffByDefault:
    def test_a_write_is_not_swallowed_when_mock_is_off(self, app):
        """Guard against the mock guard: with TRELLO_MOCK off the real call must still be made."""
        from app.trello.api import update_trello_card

        with app.app_context(), patch("app.trello.api.cfg.TRELLO_MOCK", False), \
             patch("app.trello.api.requests") as rq:
            rq.put.return_value.status_code = 200
            rq.put.return_value.json.return_value = {}
            update_trello_card(card_id="card-123", new_due_date=date(2026, 6, 15))
            rq.put.assert_called_once()
