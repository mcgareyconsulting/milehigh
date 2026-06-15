"""Tests for assigning an installer team on Start Install.

Setting an installer stores Releases.installer and moves the release's mirror
Trello card into the list matching the installer name (or Unassigned when
cleared). Date handling is unchanged; installer can be set with or without a date.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.models import Releases, ReleaseEvents, db
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


def _installer_patches():
    return (
        patch(
            "app.brain.job_log.features.start_install.assign_installer.get_list_by_name",
            return_value={"name": "Saul 2", "id": "list-saul2"},
        ),
        patch(
            "app.brain.job_log.features.start_install.assign_installer.move_mirror_card",
        ),
        patch(
            "app.brain.job_log.features.start_install.assign_installer.set_mirror_date_range",
            return_value={"success": True, "mirror_card_id": "mirror-999"},
        ),
    )


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

            p_list, p_move, p_range = _installer_patches()
            with p_list, p_move as mock_move, p_range:
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

            mock_move.assert_called_once_with("card-123", "list-saul2")

    def test_installer_only_does_not_clear_existing_date(self, app, admin_client):
        with app.app_context():
            _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            p_list, p_move, p_range = _installer_patches()
            with p_list, p_move, p_range:
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

            p_list, p_move, p_range = _installer_patches()
            p_trello, p_recalc = _date_command_patches()
            with p_list, p_move as mock_move, p_range, p_trello, p_recalc:
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
            mock_move.assert_called_once_with("card-123", "list-saul2")

    def test_clearing_installer_moves_to_unassigned(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Saul 2")
            db.session.commit()

            with patch(
                "app.brain.job_log.features.start_install.assign_installer.move_mirror_card",
            ) as mock_move, patch(
                "app.brain.job_log.features.start_install.assign_installer.Config"
            ) as mock_cfg:
                mock_cfg.UNASSIGNED_CARDS_LIST_ID = "list-unassigned"
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={"installer": ""},
                )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.installer is None
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

            p_list, p_move, p_range = _installer_patches()
            with p_list, p_move, p_range as mock_range:
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={"installer": "Saul 2"},
                )
            assert resp.status_code == 200

            mock_range.assert_called_once_with("card-123", date(2026, 6, 15), expected_comp_eta)

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.mirror_trello_card_id == "mirror-999"
            assert r2.comp_eta == expected_comp_eta
