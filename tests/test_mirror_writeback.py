"""Tests for the mirror-card date write-back (Trello -> job log, verbatim).

The mirror (installer-team) card's `start` maps to start_install and `due` maps
to comp_eta. Edits are written back verbatim; Brain's own range push is a no-op
echo (value-diff guard). Also covers the webhook parser detecting `start` changes.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.models import Releases, ReleaseEvents, db
from app.trello.utils import parse_webhook_data


def _sync_op():
    return SimpleNamespace(operation_id="test-op")


def _make_release(**kwargs):
    defaults = dict(
        job=1, release="A", job_name="Test Job",
        stage="Ship Planning", stage_group="READY_TO_SHIP",
        fab_order=2.0,
        trello_card_id="primary-1",
        mirror_trello_card_id="mirror-1",
        start_install_formulaTF=False,
    )
    defaults.update(kwargs)
    r = Releases(**defaults)
    db.session.add(r)
    db.session.flush()
    return r


# --- webhook parser detects start-date changes -----------------------------

def test_parse_webhook_detects_start_date_change():
    payload = {
        "action": {
            "type": "updateCard",
            "data": {
                "card": {"id": "mirror-1", "name": "X"},
                "old": {"start": "2026-06-10T18:00:00Z"},
            },
            "date": "2026-06-11T12:00:00Z",
            "memberCreator": {"id": "u1"},
        }
    }
    parsed = parse_webhook_data(payload)
    assert parsed["handled"] is True
    assert "start_date_change" in parsed["change_types"]
    assert parsed["has_start_date_change"] is True


# --- verbatim write-back ----------------------------------------------------

class TestMirrorWriteback:
    def test_start_and_due_written_verbatim(self, app):
        from app.trello.sync import _handle_mirror_writeback
        with app.app_context():
            r = _make_release(start_install=date(2026, 6, 1), comp_eta=date(2026, 6, 3))
            db.session.commit()

            card_data = {"start": "2026-06-20T13:00:00Z", "due": "2026-06-24T18:00:00Z"}
            event_info = {
                "change_types": ["start_date_change", "due_date_change"],
                "time": "2026-06-19T10:00:00Z",
                "trello_user_id": "u1",
            }
            with patch("app.trello.sync.update_trello_card") as mock_primary, \
                 patch("app.trello.sync.safe_log_sync_event"):
                handled = _handle_mirror_writeback("mirror-1", card_data, event_info, _sync_op())

            assert handled is True
            db.session.refresh(r)
            assert r.start_install == date(2026, 6, 20)
            assert r.comp_eta == date(2026, 6, 24)
            assert r.start_install_formulaTF is False
            # primary card due realigned to the new start_install
            mock_primary.assert_called_once()
            assert mock_primary.call_args.kwargs["new_due_date"] == date(2026, 6, 20)
            # one start event emitted
            assert ReleaseEvents.query.filter_by(action="update_start_install").count() == 1

    def test_echo_no_change_is_noop(self, app):
        from app.trello.sync import _handle_mirror_writeback
        with app.app_context():
            _make_release(start_install=date(2026, 6, 20), comp_eta=date(2026, 6, 24))
            db.session.commit()

            # Brain's own range push: the card already equals the DB.
            card_data = {"start": "2026-06-20T13:00:00Z", "due": "2026-06-24T18:00:00Z"}
            event_info = {
                "change_types": ["start_date_change", "due_date_change"],
                "time": "2026-06-19T10:00:00Z",
            }
            with patch("app.trello.sync.update_trello_card") as mock_primary, \
                 patch("app.trello.sync.safe_log_sync_event"):
                handled = _handle_mirror_writeback("mirror-1", card_data, event_info, _sync_op())

            assert handled is True
            mock_primary.assert_not_called()
            assert ReleaseEvents.query.filter_by(action="update_start_install").count() == 0

    def test_unknown_card_returns_false(self, app):
        from app.trello.sync import _handle_mirror_writeback
        with app.app_context():
            _make_release()
            db.session.commit()
            with patch("app.trello.sync.safe_log_sync_event"):
                handled = _handle_mirror_writeback(
                    "not-a-mirror",
                    {"start": None, "due": None},
                    {"change_types": ["due_date_change"]},
                    _sync_op(),
                )
            assert handled is False


class TestNumGuysRecompute:
    """Changing num_guys re-stretches the install bar from a fixed start_install:
    comp_eta = start_install + duration(install_hrs, num_guys), written to the release
    and pushed to the mirror bar's due."""

    def test_apply_num_guys_change_recomputes_comp_eta(self, app):
        from app.trello.sync import _apply_num_guys_change
        with app.app_context():
            # 2 guys, 32 hrs -> 2 install days, completes Mon 6/15 + 1 = Tue 6/16.
            r = _make_release(
                start_install=date(2026, 6, 15), comp_eta=date(2026, 6, 16),
                install_hrs=32.0, num_guys=2.0,
            )
            db.session.commit()

            with patch("app.trello.sync.set_mirror_date_range") as mock_push, \
                 patch("app.trello.sync.sync_num_guys_on_card") as mock_sync:
                changed = _apply_num_guys_change(r, 4.0, source="Trello")
                db.session.commit()

            assert changed is True
            assert r.num_guys == 4.0
            # 4 guys: ceil(32/(4*8)) = 1 install day -> completes the start day, 6/15.
            assert r.comp_eta == date(2026, 6, 15)
            # The new bar end is pushed to the mirror (start unchanged).
            mock_push.assert_called_once_with("primary-1", date(2026, 6, 15), date(2026, 6, 15))
            # Both cards are synced to the canonical value (DB is source of truth).
            synced = {c.args[0] for c in mock_sync.call_args_list}
            assert synced == {"primary-1", "mirror-1"}
            assert ReleaseEvents.query.filter_by(action="updated").count() == 1

    def test_mirror_description_num_guys_recomputes_comp_eta(self, app):
        from app.trello.sync import _handle_mirror_writeback
        with app.app_context():
            r = _make_release(
                start_install=date(2026, 6, 15), comp_eta=date(2026, 6, 16),
                install_hrs=32.0, num_guys=2.0,
            )
            db.session.commit()

            card_data = {"desc": "**Number of Guys:** 4"}
            event_info = {"change_types": ["description_change"], "time": "2026-06-12T10:00:00Z"}
            with patch("app.trello.sync.set_mirror_date_range"), \
                 patch("app.trello.sync.sync_num_guys_on_card"), \
                 patch("app.trello.sync.safe_log_sync_event"):
                handled = _handle_mirror_writeback("mirror-1", card_data, event_info, _sync_op())

            assert handled is True
            db.session.refresh(r)
            assert r.num_guys == 4.0
            assert r.comp_eta == date(2026, 6, 15)

    def test_num_guys_unchanged_is_noop(self, app):
        from app.trello.sync import _apply_num_guys_change
        with app.app_context():
            r = _make_release(
                start_install=date(2026, 6, 15), comp_eta=date(2026, 6, 16),
                install_hrs=32.0, num_guys=2.0,
            )
            db.session.commit()
            with patch("app.trello.sync.set_mirror_date_range") as mock_push, \
                 patch("app.trello.sync.sync_num_guys_on_card") as mock_sync:
                changed = _apply_num_guys_change(r, 2.0, source="Trello")
            assert changed is False
            mock_push.assert_not_called()
            mock_sync.assert_not_called()
