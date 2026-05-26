"""Tests for the installer-team timeline: gantt-data grouped by installer lane,
and comp_eta persistence from end-edge resize / move drags.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.models import Releases, ReleaseEvents, db


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        yield


def _make_release(job, release, **kwargs):
    defaults = dict(
        job=job,
        release=release,
        job_name="Test Job",
        stage="Paint Start",
        stage_group="FABRICATION",
        fab_order=12.5,
        start_install=date(2026, 6, 1),
        start_install_formulaTF=False,
        start_install_asap=False,
        install_hrs=24.0,
        installer="Octavio",
        trello_card_id=f"card-{job}-{release}",
    )
    defaults.update(kwargs)
    r = Releases(**defaults)
    db.session.add(r)
    db.session.flush()
    return r


def _date_command_patches():
    return (
        patch("app.brain.job_log.features.start_install.command.update_trello_card"),
        patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"),
    )


class TestGanttData:
    def test_groups_by_installer_team(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Octavio")
            _make_release(2, "B", installer="Oscar")
            db.session.commit()

            resp = admin_client.get("/brain/gantt-data")
            assert resp.status_code == 200
            teams = {t["team"]: t for t in resp.get_json()["teams"]}

            # Configured lanes are always present (Octavio, Saul 2, Oscar by default).
            assert "Octavio" in teams
            assert "Oscar" in teams
            assert len(teams["Octavio"]["releases"]) == 1
            assert teams["Octavio"]["releases"][0]["release"] == "A"
            assert teams["Octavio"]["releases"][0]["team"] == "Octavio"

    def test_excludes_releases_without_installer(self, app, admin_client):
        with app.app_context():
            _make_release(3, "C", installer=None)
            db.session.commit()

            resp = admin_client.get("/brain/gantt-data")
            all_releases = [
                r for t in resp.get_json()["teams"] for r in t["releases"]
            ]
            assert all(r["release"] != "C" for r in all_releases)

    def test_prefers_stored_comp_eta_over_computed(self, app, admin_client):
        with app.app_context():
            # install_hrs=24 would compute comp_eta = start + 1 day = 6/2, but a stored
            # comp_eta override must win.
            _make_release(4, "D", comp_eta=date(2026, 6, 10))
            db.session.commit()

            resp = admin_client.get("/brain/gantt-data")
            octavio = next(t for t in resp.get_json()["teams"] if t["team"] == "Octavio")
            bar = next(r for r in octavio["releases"] if r["release"] == "D")
            assert bar["endDate"] == "2026-06-10"

    def test_computes_comp_eta_when_unset(self, app, admin_client):
        with app.app_context():
            _make_release(5, "E", comp_eta=None, install_hrs=24.0)
            db.session.commit()

            resp = admin_client.get("/brain/gantt-data")
            octavio = next(t for t in resp.get_json()["teams"] if t["team"] == "Octavio")
            bar = next(r for r in octavio["releases"] if r["release"] == "E")
            # start 6/1 + ceil(24/24)=1 day
            assert bar["endDate"] == "2026-06-02"


class TestCompEtaPersistence:
    def test_comp_eta_only_does_not_clear_start_install(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"comp_eta": "2026-06-20"},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.comp_eta == date(2026, 6, 20)
            assert r2.start_install == date(2026, 6, 1)
            assert r2.start_install_formulaTF is False

    def test_start_install_and_comp_eta_together(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            p_trello, p_recalc = _date_command_patches()
            with p_trello, p_recalc:
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={"start_install": "2026-07-01", "comp_eta": "2026-07-05"},
                )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install == date(2026, 7, 1)
            assert r2.comp_eta == date(2026, 7, 5)

    def test_comp_eta_change_records_event(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", comp_eta=date(2026, 6, 5))
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"comp_eta": "2026-06-12"},
            )
            assert resp.status_code == 200

            evs = ReleaseEvents.query.filter_by(action="update_comp_eta").all()
            assert len(evs) == 1
            assert evs[0].payload["from"] == "2026-06-05"
            assert evs[0].payload["to"] == "2026-06-12"

    def test_comp_eta_unchanged_emits_no_event(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", comp_eta=date(2026, 6, 5))
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"comp_eta": "2026-06-05"},
            )
            assert resp.status_code == 200

            assert ReleaseEvents.query.filter_by(action="update_comp_eta").count() == 0

    def test_comp_eta_with_installer_change(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", installer="Octavio")
            db.session.commit()

            with patch(
                "app.brain.job_log.features.start_install.assign_installer.get_list_by_name",
                return_value={"name": "Saul 2", "id": "list-saul2"},
            ), patch(
                "app.brain.job_log.features.start_install.assign_installer.move_mirror_card",
            ):
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={"comp_eta": "2026-06-25", "installer": "Saul 2"},
                )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.comp_eta == date(2026, 6, 25)
            assert r2.installer == "Saul 2"
