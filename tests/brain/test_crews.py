"""Tests for installer crews (the `installer_teams` table) and crew-driven ETA.

Crews are admin-managed via the PM board "Edit Crews" UI. A crew's `crew_size`
(number of installers) drives the completion ETA of every release assigned to
that crew: comp_eta = start_install + ceil(install_hrs / (crew_size × 8h))
business days. Changing a crew's size reflows scheduling.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.models import Releases, InstallerTeam, db
from app.brain.job_log.scheduling.calculator import calculate_install_complete_date


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        yield


def _make_release(job, release, **kwargs):
    defaults = dict(
        job=job,
        release=release,
        job_name="Test Job",
        stage="Released",
        stage_group="FABRICATION",
        fab_order=12.5,
        fab_hrs=80.0,
        install_hrs=40.0,
        start_install_formulaTF=True,  # formula-driven so recalc updates it
    )
    defaults.update(kwargs)
    r = Releases(**defaults)
    db.session.add(r)
    db.session.flush()
    return r


class TestCompEtaCrewSize:
    """Direct unit coverage of the crew-size-aware install-complete formula."""

    def test_none_crew_matches_explicit_two(self):
        start = date(2026, 6, 1)
        assert (
            calculate_install_complete_date(start, 40.0, None)
            == calculate_install_complete_date(start, 40.0, 2)
        )

    def test_larger_crew_finishes_no_later(self):
        start = date(2026, 6, 1)
        two = calculate_install_complete_date(start, 40.0, 2)
        three = calculate_install_complete_date(start, 40.0, 3)
        four = calculate_install_complete_date(start, 40.0, 4)
        assert two > start
        assert three <= two
        assert four <= three

    def test_zero_crew_falls_back(self):
        start = date(2026, 6, 1)
        assert (
            calculate_install_complete_date(start, 40.0, 0)
            == calculate_install_complete_date(start, 40.0, None)
        )


class TestCrewDrivenRecalc:
    def test_assigned_crew_size_drives_comp_eta(self, app):
        """A release assigned to a bigger crew gets an earlier (or equal) comp_eta."""
        from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling

        with app.app_context():
            db.session.add(InstallerTeam(name="Small", crew_size=1))
            db.session.add(InstallerTeam(name="Big", crew_size=4))
            _make_release(1, "A", installer="Small")
            db.session.commit()

            recalculate_all_jobs_scheduling(reference_date=date(2026, 4, 1))
            db.session.expire_all()
            small_eta = Releases.query.filter_by(job=1, release="A").first().comp_eta

            r = Releases.query.filter_by(job=1, release="A").first()
            r.installer = "Big"
            db.session.commit()
            recalculate_all_jobs_scheduling(reference_date=date(2026, 4, 1))
            db.session.expire_all()
            big_eta = Releases.query.filter_by(job=1, release="A").first().comp_eta

            assert small_eta is not None and big_eta is not None
            assert big_eta <= small_eta  # 40/(4*8)=2d  vs  40/(1*8)=5d


class TestCrewCrud:
    def test_create_and_list_crew(self, app, admin_client):
        with app.app_context():
            resp = admin_client.post("/brain/crews", json={"name": "Octavio", "crew_size": 3})
            assert resp.status_code == 201
            assert resp.get_json()["crew_size"] == 3

            listing = admin_client.get("/brain/crews").get_json()["crews"]
            assert any(c["name"] == "Octavio" and c["crew_size"] == 3 for c in listing)

    def test_create_requires_name(self, app, admin_client):
        with app.app_context():
            resp = admin_client.post("/brain/crews", json={"name": "  "})
            assert resp.status_code == 400

    def test_duplicate_name_rejected(self, app, admin_client):
        with app.app_context():
            db.session.add(InstallerTeam(name="Saul 2", crew_size=2))
            db.session.commit()
            resp = admin_client.post("/brain/crews", json={"name": "Saul 2"})
            assert resp.status_code == 409

    def test_non_admin_cannot_create(self, app, non_admin_client):
        with app.app_context():
            resp = non_admin_client.post("/brain/crews", json={"name": "Nope", "crew_size": 2})
            assert resp.status_code == 403

    def test_update_crew_size_triggers_recalc(self, app, admin_client):
        with app.app_context():
            crew = InstallerTeam(name="Oscar", crew_size=2)
            db.session.add(crew)
            db.session.commit()
            crew_id = crew.id

            with patch(
                "app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"
            ) as mock_recalc:
                resp = admin_client.patch(f"/brain/crews/{crew_id}", json={"crew_size": 5})
            assert resp.status_code == 200
            assert resp.get_json()["crew_size"] == 5
            mock_recalc.assert_called_once()

    def test_rename_crew_syncs_release_installer(self, app, admin_client):
        with app.app_context():
            crew = InstallerTeam(name="Old Name", crew_size=2)
            db.session.add(crew)
            _make_release(1, "A", installer="Old Name")
            db.session.commit()
            crew_id = crew.id

            resp = admin_client.patch(f"/brain/crews/{crew_id}", json={"name": "New Name"})
            assert resp.status_code == 200

            db.session.expire_all()
            r = Releases.query.filter_by(job=1, release="A").first()
            assert r.installer == "New Name"

    def test_delete_crew(self, app, admin_client):
        with app.app_context():
            crew = InstallerTeam(name="Temp", crew_size=2)
            db.session.add(crew)
            db.session.commit()
            crew_id = crew.id

            with patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
                resp = admin_client.delete(f"/brain/crews/{crew_id}")
            assert resp.status_code == 200
            assert InstallerTeam.query.get(crew_id) is None


class TestGanttData:
    def test_gantt_data_is_installer_laned(self, app, admin_client):
        """/gantt-data returns one lane per active crew; eligible releases land in
        their crew's lane."""
        with app.app_context():
            db.session.add(InstallerTeam(name="Octavio", crew_size=3))
            db.session.add(InstallerTeam(name="Empty Crew", crew_size=2))
            _make_release(
                1, "A",
                installer="Octavio",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,  # hard date → timeline-eligible
                install_hrs=40.0,
            )
            db.session.commit()

            data = admin_client.get("/brain/gantt-data").get_json()
            assert "teams" in data
            lanes = {t["team"]: t for t in data["teams"]}
            assert "Octavio" in lanes and "Empty Crew" in lanes
            assert len(lanes["Octavio"]["releases"]) == 1
            assert lanes["Octavio"]["releases"][0]["job"] == 1
            assert lanes["Empty Crew"]["releases"] == []


class TestTimelineBar:
    def test_skip_trello_sets_comp_eta_without_pushing(self, app, admin_client):
        """A timeline drag (skip_trello) sets start_install + comp_eta and does NOT
        push an outbound Trello due-date change."""
        with app.app_context():
            _make_release(1, "A", trello_card_id="card-xyz", start_install_formulaTF=True)
            db.session.commit()

            with patch(
                "app.brain.job_log.features.start_install.command.update_trello_card"
            ) as mock_push, patch(
                "app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"
            ):
                resp = admin_client.patch(
                    "/brain/update-start-install/1/A",
                    json={
                        "start_install": "2026-06-10",
                        "comp_eta": "2026-06-13",
                        "is_hard_date": True,
                        "skip_trello": True,
                    },
                )
            assert resp.status_code == 200
            mock_push.assert_not_called()

            db.session.expire_all()
            r = Releases.query.filter_by(job=1, release="A").first()
            assert r.start_install == date(2026, 6, 10)
            assert r.comp_eta == date(2026, 6, 13)
            assert r.start_install_formulaTF is False

    def test_comp_eta_only_does_not_clear_start_install(self, app, admin_client):
        """A bar resize sends comp_eta only — start_install must be preserved."""
        with app.app_context():
            _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"comp_eta": "2026-06-09", "is_hard_date": True, "skip_trello": True},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r = Releases.query.filter_by(job=1, release="A").first()
            assert r.start_install == date(2026, 6, 1)
            assert r.comp_eta == date(2026, 6, 9)


class TestInstallerTeamsEndpoint:
    def test_installer_teams_returns_db_crews(self, app, admin_client):
        with app.app_context():
            db.session.add(InstallerTeam(name="Crew Z", crew_size=2, is_active=True))
            db.session.add(InstallerTeam(name="Crew A", crew_size=2, is_active=True))
            db.session.commit()

            names = admin_client.get("/brain/installer-teams").get_json()["installer_teams"]
            assert "Crew A" in names and "Crew Z" in names
