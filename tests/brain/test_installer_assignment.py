"""Tests for assigning an installer team on Start Install.

Setting an installer stores Releases.installer synchronously and QUEUES the mirror Trello card's
move (and date bar) onto TrelloOutbox — it is never called inline. Date handling is unchanged;
installer can be set with or without a date.

So the tests come in two layers: the route/command layer asserts the DB write plus an enqueued,
still-open outbox item; the delivery layer drains the outbox with the Trello API patched and
asserts the calls that actually reach the board.
"""
from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.models import Releases, ReleaseEvents, TrelloOutbox, db
from app.services.outbox_service import OutboxService
from tests.conftest import make_release


@pytest.fixture(autouse=True)
def setup_auth(admin_session):
    yield


def _make_release(job, release, **kwargs):
    """Installer-flow release: Paint Start, formula-driven date, mirror card."""
    return make_release(job, release, **{
        "stage": "Paint Start",
        "fab_order": 12.5,
        "start_install_formulaTF": True,
        "start_install_asap": False,
        "trello_card_id": "card-123",
        **kwargs,
    })


def _installer_patches(list_id="list-saul2"):
    """Patch the Trello calls the OUTBOX makes — the command itself no longer touches Trello."""
    return (
        patch(
            "app.trello.api.get_list_by_name",
            return_value=({"name": "Saul 2", "id": list_id} if list_id else None),
        ),
        patch("app.trello.api.move_mirror_card"),
        patch(
            "app.trello.api.set_mirror_date_range",
            return_value={"success": True, "mirror_card_id": "mirror-999"},
        ),
    )


def _pending_outbox(action="assign_installer"):
    return TrelloOutbox.query.filter_by(action=action, status="pending").all()


def _drain_outbox():
    """Run every pending outbox item, as the retry worker would."""
    return OutboxService.process_pending_items(limit=50)


def _date_command_patches():
    return (
        patch("app.brain.job_log.features.start_install.command.update_trello_card"),
        patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"),
    )


class TestAssignInstallerRoute:
    def test_installer_only_sets_column_and_moves_mirror(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": "Saul 2"},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.installer == "Saul 2"

            evs = ReleaseEvents.query.filter_by(action="update_installer").all()
            assert len(evs) == 1
            assert evs[0].payload["from"] is None
            assert evs[0].payload["to"] == "Saul 2"
            # The DB write lands now; the board call is queued, not made, and the event stays
            # open until it is delivered.
            assert evs[0].applied_at is None
            assert len(_pending_outbox()) == 1

            p_list, p_move, p_range = _installer_patches()
            with p_list, p_move as mock_move, p_range:
                _drain_outbox()
            mock_move.assert_called_once_with("card-123", "list-saul2")

            db.session.expire_all()
            assert ReleaseEvents.query.filter_by(action="update_installer").one().applied_at is not None

    def test_installer_only_does_not_clear_existing_date(self, app, admin_client):
        with app.app_context():
            _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": "Saul 2"},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install == date(2026, 6, 1)
            assert r2.start_install_formulaTF is False
            assert r2.installer == "Saul 2"

    def test_date_and_installer_together(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            p_trello, p_recalc = _date_command_patches()
            with p_trello, p_recalc:
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={"start_install": "2026-06-15", "installer": "Saul 2"},
                )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install == date(2026, 6, 15)
            assert r2.start_install_formulaTF is False
            assert r2.installer == "Saul 2"

            assert ReleaseEvents.query.filter_by(action="update_start_install").count() == 1
            assert ReleaseEvents.query.filter_by(action="update_installer").count() == 1

            p_list, p_move, p_range = _installer_patches()
            with p_list, p_move as mock_move, p_range:
                _drain_outbox()
            mock_move.assert_called_once_with("card-123", "list-saul2")

    def test_clearing_installer_moves_to_unassigned(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Saul 2")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": ""},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.installer is None

            with patch("app.trello.api.move_mirror_card") as mock_move, patch(
                "app.config.Config.UNASSIGNED_CARDS_LIST_ID", "list-unassigned", create=True
            ):
                _drain_outbox()
            mock_move.assert_called_once_with("card-123", "list-unassigned")

    def test_assign_installer_seeds_mirror_date_range(self, app, admin_client):
        """Assigning an installer to a dated release seeds the mirror card's date bar to
        [start_install, comp_eta] and persists the mirror card id."""
        from app.brain.job_log.scheduling.calculator import calculate_install_complete_date

        with app.app_context():
            _make_release(
                1, "A",
                start_install=date(2026, 6, 15),
                start_install_formulaTF=False,
                install_hrs=32.0,
                num_guys=2.0,
            )
            db.session.commit()

            expected_comp_eta = calculate_install_complete_date(date(2026, 6, 15), 32.0, 2.0)

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": "Saul 2"},
            )
            assert resp.status_code == 200

            # comp_eta is DB truth and lands immediately, before any Trello delivery.
            db.session.expire_all()
            assert Releases.query.filter_by(job=1, release="A").first().comp_eta == expected_comp_eta

            p_list, p_move, p_range = _installer_patches()
            with p_list, p_move, p_range as mock_range:
                _drain_outbox()
            mock_range.assert_called_once_with("card-123", date(2026, 6, 15), expected_comp_eta)

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.mirror_trello_card_id == "mirror-999"
            assert r2.comp_eta == expected_comp_eta


class TestInstallerUndo:
    """A Timeline drag writes the installer, so a mis-drop has to be reversible.

    The drag sends date + installer in one PATCH, which lands two events; the installer event
    carries the date event's id as `parent_event_id` so a single Undo reverses the whole drop.
    """

    def test_installer_change_is_undoable(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Saul 1")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": "Saul 2"},
            )
            assert resp.status_code == 200
            event_id = resp.get_json()["event_id"]

            undo = admin_client.post(f"/brain/events/{event_id}/undo")
            assert undo.status_code == 200, undo.get_data(as_text=True)

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.installer == "Saul 1"

    def test_undo_walks_the_mirror_card_back_to_the_old_crew(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Saul 1")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": "Saul 2"},
            )
            event_id = resp.get_json()["event_id"]

            undo = admin_client.post(f"/brain/events/{event_id}/undo")
            assert undo.status_code == 200

            # Two queued deliveries — out to Saul 2, then back to Saul 1 — so the mirror is walked
            # back on the undo too, just not inline.
            assert len(_pending_outbox()) == 2

            with patch("app.trello.api.get_list_by_name", return_value={"name": "Saul 1", "id": "list-saul1"}), \
                 patch("app.trello.api.move_mirror_card") as mock_move, \
                 patch("app.trello.api.set_mirror_date_range", return_value={"success": True}):
                _drain_outbox()

            # Both items resolve against the row's CURRENT installer, so the board converges on
            # Saul 1 rather than replaying a stale hop through Saul 2.
            assert mock_move.call_count == 2
            assert {c.args[1] for c in mock_move.call_args_list} == {"list-saul1"}

    def test_undo_of_an_unassign_puts_the_crew_back(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Saul 2")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": ""},
            )
            assert resp.status_code == 200
            event_id = resp.get_json()["event_id"]

            undo = admin_client.post(f"/brain/events/{event_id}/undo")
            assert undo.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.installer == "Saul 2"

    def test_a_drag_links_both_events_so_one_undo_reverses_the_whole_drop(self, app, admin_client):
        """The shape a Timeline drop actually sends: date + installer in one request."""
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            p_trello, p_recalc = _date_command_patches()
            with p_trello, p_recalc:
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={"start_install": "2026-06-15", "installer": "Saul 2"},
                )
            assert resp.status_code == 200
            date_event_id = resp.get_json()["event_id"]

            installer_ev = ReleaseEvents.query.filter_by(action="update_installer").one()
            assert installer_ev.payload["parent_event_id"] == date_event_id

            # Undoing the date event should take the installer with it.
            with p_trello, p_recalc:
                undo = admin_client.post(f"/brain/events/{date_event_id}/undo")
            assert undo.status_code == 200, undo.get_data(as_text=True)

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.installer is None, "the installer half of the drop was left behind"
            assert r2.start_install is None

    def test_undo_is_refused_when_someone_reassigned_in_the_meantime(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Saul 1")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": "Saul 2"},
            )
            event_id = resp.get_json()["event_id"]

            # Somebody else moves it on before the undo lands.
            r = Releases.query.filter_by(job=1, release="A").first()
            r.installer = "Saul 3"
            db.session.commit()

            undo = admin_client.post(f"/brain/events/{event_id}/undo")
            assert undo.status_code == 409
            assert undo.get_json()["error"] == "stale"

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.installer == "Saul 3", "a stale undo must not overwrite the later change"

    def test_events_list_marks_an_installer_change_undoable(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Saul 1")
            db.session.commit()

            admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"installer": "Saul 2"},
            )

            resp = admin_client.get("/brain/events?limit=50")
            assert resp.status_code == 200
            ev = next(e for e in resp.get_json()["events"] if e["action"] == "update_installer")
            assert ev["current_value"] == "Saul 2"


class TestInstallerOutboxDelivery:
    """The point of routing the mirror through the outbox: a failed board call is retried with
    backoff and finally logged as an ERROR, instead of being swallowed while the Brain reports
    success. Before this change every one of these cases was a silent warning."""

    def _assign(self, admin_client, installer="Saul 2"):
        resp = admin_client.patch(
            "/brain/update-start-install/1/A", json={"installer": installer}
        )
        assert resp.status_code == 200
        return TrelloOutbox.query.filter_by(action="assign_installer").one()

    def test_the_request_makes_no_trello_call_at_all(self, app, admin_client):
        """The whole latency argument: a drop must not block on Trello round-trips."""
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            with patch("app.trello.api.move_mirror_card") as mock_move, \
                 patch("app.trello.api.set_mirror_date_range") as mock_range, \
                 patch("app.trello.api.get_list_by_name") as mock_list:
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A", json={"installer": "Saul 2"}
                )
            assert resp.status_code == 200
            mock_move.assert_not_called()
            mock_range.assert_not_called()
            mock_list.assert_not_called()

    def test_a_failed_move_is_retried_with_backoff_not_swallowed(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()
            item = self._assign(admin_client)

            with patch("app.trello.api.get_list_by_name", return_value={"name": "Saul 2", "id": "list-saul2"}), \
                 patch("app.trello.api.move_mirror_card", side_effect=RuntimeError("Trello 503")):
                _drain_outbox()

            db.session.expire_all()
            item = db.session.get(TrelloOutbox, item.id)
            assert item.status == "pending", "a failed delivery must stay queued"
            assert item.retry_count == 1
            assert "Trello 503" in item.error_message
            assert item.next_retry_at > datetime.utcnow()
            # Still open — the release is not considered synced until it actually is.
            assert ReleaseEvents.query.filter_by(action="update_installer").one().applied_at is None

    def test_delivery_finally_fails_loudly_after_exhausting_retries(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()
            item = self._assign(admin_client)
            item.retry_count = item.max_retries - 1
            db.session.commit()

            with patch("app.trello.api.get_list_by_name", return_value={"name": "Saul 2", "id": "list-saul2"}), \
                 patch("app.trello.api.move_mirror_card", side_effect=RuntimeError("Trello down")):
                _drain_outbox()

            db.session.expire_all()
            assert db.session.get(TrelloOutbox, item.id).status == "failed"

    def test_a_retry_eventually_succeeds_and_closes_the_event(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()
            item = self._assign(admin_client)

            with patch("app.trello.api.get_list_by_name", return_value={"name": "Saul 2", "id": "list-saul2"}), \
                 patch("app.trello.api.move_mirror_card", side_effect=RuntimeError("blip")):
                _drain_outbox()

            db.session.expire_all()
            item = db.session.get(TrelloOutbox, item.id)
            item.next_retry_at = datetime.utcnow()   # skip the backoff wait
            db.session.commit()

            with patch("app.trello.api.get_list_by_name", return_value={"name": "Saul 2", "id": "list-saul2"}), \
                 patch("app.trello.api.move_mirror_card") as mock_move, \
                 patch("app.trello.api.set_mirror_date_range", return_value={"success": True}):
                _drain_outbox()

            mock_move.assert_called_once_with("card-123", "list-saul2")
            db.session.expire_all()
            assert db.session.get(TrelloOutbox, item.id).status == "completed"
            assert ReleaseEvents.query.filter_by(action="update_installer").one().applied_at is not None

    def test_an_installer_with_no_matching_list_is_retried_then_surfaced(self, app, admin_client):
        """This used to be a warning and a shrug — the assignment reported success and the mirror
        never moved. Now it retries (the cache may just be cold) and then fails visibly."""
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()
            item = self._assign(admin_client, installer="Nobody")

            with patch("app.trello.api.get_list_by_name", return_value=None), \
                 patch("app.trello.api.move_mirror_card") as mock_move:
                _drain_outbox()

            mock_move.assert_not_called()
            db.session.expire_all()
            item = db.session.get(TrelloOutbox, item.id)
            assert item.status == "pending"
            assert "Nobody" in item.error_message

    def test_rapid_reassignment_converges_on_the_current_crew(self, app, admin_client):
        """The Timeline makes it easy to drop a release twice in a second. Both queued items read
        the live row, so the board lands on the latest crew instead of replaying a stale hop."""
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            admin_client.patch("/brain/update-start-install/1/A", json={"installer": "Saul 2"})
            admin_client.patch("/brain/update-start-install/1/A", json={"installer": "Saul 3"})

            assert len(_pending_outbox()) == 2
            db.session.expire_all()
            assert Releases.query.filter_by(job=1, release="A").first().installer == "Saul 3"

            with patch("app.trello.api.get_list_by_name", return_value={"name": "Saul 3", "id": "list-saul3"}), \
                 patch("app.trello.api.move_mirror_card") as mock_move, \
                 patch("app.trello.api.set_mirror_date_range", return_value={"success": True}):
                _drain_outbox()

            assert {c.args[1] for c in mock_move.call_args_list} == {"list-saul3"}

    def test_a_missing_linked_mirror_does_not_retry_forever(self, app, admin_client):
        """No mirror card on the board is a fact, not a delivery failure — retrying can't make one."""
        with app.app_context():
            _make_release(
                1, "A",
                start_install=date(2026, 6, 15),
                start_install_formulaTF=False,
            )
            db.session.commit()
            item = self._assign(admin_client)

            with patch("app.trello.api.get_list_by_name", return_value={"name": "Saul 2", "id": "list-saul2"}), \
                 patch("app.trello.api.move_mirror_card"), \
                 patch("app.trello.api.set_mirror_date_range",
                       return_value={"success": False, "error": "no linked mirror card"}):
                _drain_outbox()

            db.session.expire_all()
            assert db.session.get(TrelloOutbox, item.id).status == "completed"

    def test_a_release_with_no_trello_card_queues_nothing_and_closes(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", trello_card_id=None)
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A", json={"installer": "Saul 2"}
            )
            assert resp.status_code == 200

            assert TrelloOutbox.query.filter_by(action="assign_installer").count() == 0
            db.session.expire_all()
            assert ReleaseEvents.query.filter_by(action="update_installer").one().applied_at is not None
