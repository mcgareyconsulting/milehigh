"""Tests for the admin Subs installer-invoice-paid page API."""
from datetime import date

import pytest

from app.models import Releases, ReleaseEvents, db
from tests.conftest import make_release


def _seed(app):
    """Three assigned live rows + fixtures for archive / inactive / unassigned."""
    with app.app_context():
        make_release(
            100, "1", job_name="Alpha",
            installer="Saul 2", stage="Install Complete",
            start_install=date(2026, 6, 1), job_comp="X",
            is_active=True, is_archived=False,
        )
        make_release(
            200, "2", job_name="Bravo",
            installer="Octavio", stage="Install Start",
            start_install=date(2026, 6, 10),
            is_active=True, is_archived=False,
            installer_invoice_paid=True,
        )
        make_release(
            150, "3", job_name="Charlie",
            installer="Octavio", stage="Install Complete",
            is_active=True, is_archived=False,
        )
        # Should be excluded: no installer
        make_release(
            300, "9", job_name="Unassigned",
            installer=None, is_active=True, is_archived=False,
        )
        # Should be excluded: archived + already invoiced complete
        make_release(
            400, "1", job_name="Archived Complete",
            installer="Octavio", is_active=True, is_archived=True,
            installer_invoice_paid=True,
        )
        # Should be excluded: inactive soft-deleted (Oscar would also be filtered)
        make_release(
            500, "1", job_name="Inactive",
            installer="Saul 2", is_active=False, is_archived=False,
        )
        # Should APPEAR: archived with outstanding sub balance
        make_release(
            450, "7", job_name="Archived Outstanding",
            installer="Saul 2", stage="Install Complete",
            is_active=True, is_archived=True,
            installer_invoice_paid=False,
            installer_invoice_numbers="INV-ARCH-7",
        )
        db.session.commit()


class TestListSubsReleases:
    def test_unauthenticated_returns_401(self, client, app):
        _seed(app)
        resp = client.get("/brain/subs/releases")
        assert resp.status_code == 401

    def test_non_admin_returns_403(self, non_admin_client, app):
        _seed(app)
        resp = non_admin_client.get("/brain/subs/releases")
        assert resp.status_code == 403

    def test_admin_list_filters_and_sorts(self, admin_client, app):
        _seed(app)
        resp = admin_client.get("/brain/subs/releases")
        assert resp.status_code == 200
        data = resp.get_json()
        releases = data["releases"]
        # Three live assigned + one archived outstanding
        assert len(releases) == 4
        keys = [(r["installer"], r["job"], r["release"]) for r in releases]
        assert keys == [
            ("Octavio", 150, "3"),
            ("Octavio", 200, "2"),
            ("Saul 2", 100, "1"),
            ("Saul 2", 450, "7"),
        ]
        assert data["installers"] == ["Octavio", "Saul 2"]
        by_job = {r["job"]: r for r in releases}
        assert by_job[200]["installer_invoice_paid"] is True
        assert by_job[100]["installer_invoice_paid"] is False
        assert by_job[450]["is_archived"] is True
        assert by_job[450]["installer_invoice_paid"] is False
        # Archived already-complete is hidden
        assert 400 not in by_job

    def test_paid_filter(self, admin_client, app):
        _seed(app)
        unpaid = admin_client.get("/brain/subs/releases?paid=false").get_json()["releases"]
        paid = admin_client.get("/brain/subs/releases?paid=true").get_json()["releases"]
        assert {r["job"] for r in unpaid} == {100, 150, 450}
        assert {r["job"] for r in paid} == {200}

    def test_installer_filter(self, admin_client, app):
        _seed(app)
        data = admin_client.get("/brain/subs/releases?installer=Octavio").get_json()
        assert {r["job"] for r in data["releases"]} == {150, 200}
        # installers roster stays full so the dropdown doesn't collapse
        assert data["installers"] == ["Octavio", "Saul 2"]

    def test_search_q(self, admin_client, app):
        _seed(app)
        by_name = admin_client.get("/brain/subs/releases?q=Alpha").get_json()["releases"]
        assert {r["job"] for r in by_name} == {100}

        by_inv = admin_client.get("/brain/subs/releases?q=INV-ARCH").get_json()["releases"]
        assert {r["job"] for r in by_inv} == {450}

        by_job = admin_client.get("/brain/subs/releases?q=150").get_json()["releases"]
        assert {r["job"] for r in by_job} == {150}

        none = admin_client.get("/brain/subs/releases?q=zzznomatch").get_json()["releases"]
        assert none == []

    def test_archived_drops_after_marked_complete(self, admin_client, app):
        _seed(app)
        before = admin_client.get("/brain/subs/releases").get_json()["releases"]
        assert any(r["job"] == 450 for r in before)

        resp = admin_client.patch(
            "/brain/subs/releases/450/7/installer-invoice-paid",
            json={"installer_invoice_paid": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["is_archived"] is True

        after = admin_client.get("/brain/subs/releases").get_json()["releases"]
        assert all(r["job"] != 450 for r in after)

    def test_oscar_excluded_from_subs_invoice_tab(self, admin_client, app):
        """Oscar is an installer crew but not a sub — hide from Invoice Paid only."""
        _seed(app)
        with app.app_context():
            make_release(
                600, "1", job_name="Oscar Crew Work",
                installer="Oscar", stage="Install Start",
                is_active=True, is_archived=False,
            )
            db.session.commit()

        data = admin_client.get("/brain/subs/releases").get_json()
        assert all(r["installer"] != "Oscar" for r in data["releases"])
        assert "Oscar" not in data["installers"]
        # Sub crews still present
        assert set(data["installers"]) == {"Octavio", "Saul 2"}

        filtered = admin_client.get("/brain/subs/releases?installer=Oscar").get_json()
        assert filtered["releases"] == []


class TestUpdateInstallerInvoicePaid:
    def test_unauthenticated_returns_401(self, client, app):
        _seed(app)
        resp = client.patch(
            "/brain/subs/releases/100/1/installer-invoice-paid",
            json={"installer_invoice_paid": True},
        )
        assert resp.status_code == 401

    def test_non_admin_returns_403(self, non_admin_client, app):
        _seed(app)
        resp = non_admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-paid",
            json={"installer_invoice_paid": True},
        )
        assert resp.status_code == 403

    def test_missing_release_returns_404(self, admin_client, app):
        _seed(app)
        resp = admin_client.patch(
            "/brain/subs/releases/999/Z/installer-invoice-paid",
            json={"installer_invoice_paid": True},
        )
        assert resp.status_code == 404

    def test_missing_body_field_returns_400(self, admin_client, app):
        _seed(app)
        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-paid",
            json={},
        )
        assert resp.status_code == 400

    def test_toggle_true_then_false_writes_events(self, admin_client, app):
        _seed(app)

        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-paid",
            json={"installer_invoice_paid": True},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["installer_invoice_paid"] is True
        assert body["changed"] is True
        assert body["event_id"] is not None

        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            assert r.installer_invoice_paid is True
            events = ReleaseEvents.query.filter_by(
                job=100, release="1", action="update_installer_invoice_paid"
            ).all()
            assert len(events) == 1
            assert events[0].payload == {"from": False, "to": True}

        resp2 = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-paid",
            json={"installer_invoice_paid": False},
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["installer_invoice_paid"] is False

        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            assert r.installer_invoice_paid is False
            events = ReleaseEvents.query.filter_by(
                job=100, release="1", action="update_installer_invoice_paid"
            ).order_by(ReleaseEvents.id).all()
            assert len(events) == 2
            assert events[1].payload == {"from": True, "to": False}

    def test_same_value_is_noop_no_event(self, admin_client, app):
        _seed(app)
        # Seed row 200 already paid=True
        resp = admin_client.patch(
            "/brain/subs/releases/200/2/installer-invoice-paid",
            json={"installer_invoice_paid": True},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["changed"] is False
        assert body["event_id"] is None
        assert body["installer_invoice_paid"] is True

        with app.app_context():
            events = ReleaseEvents.query.filter_by(
                job=200, release="2", action="update_installer_invoice_paid"
            ).all()
            assert events == []


class TestInstallerInvoiceProgress:
    def test_list_includes_progress_and_numbers(self, admin_client, app):
        _seed(app)
        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            r.installer_invoice_progress = 40
            r.installer_invoice_numbers = "INV-1\nINV-2"
            db.session.commit()

        data = admin_client.get("/brain/subs/releases").get_json()
        by_job = {row["job"]: row for row in data["releases"]}
        assert by_job[100]["installer_invoice_progress"] == 40
        assert by_job[100]["installer_invoice_numbers"] == "INV-1\nINV-2"
        assert by_job[150]["installer_invoice_progress"] is None
        assert by_job[150]["installer_invoice_numbers"] == ""

    def test_set_progress_and_clear(self, admin_client, app):
        _seed(app)
        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-progress",
            json={"installer_invoice_progress": 75},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["installer_invoice_progress"] == 75
        assert body["changed"] is True
        assert body["event_id"] is not None

        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            assert r.installer_invoice_progress == 75
            events = ReleaseEvents.query.filter_by(
                job=100, release="1", action="update_installer_invoice_progress"
            ).all()
            assert len(events) == 1
            assert events[0].payload == {"from": None, "to": 75}

        clear = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-progress",
            json={"installer_invoice_progress": None},
        )
        assert clear.status_code == 200
        assert clear.get_json()["installer_invoice_progress"] is None

        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            assert r.installer_invoice_progress is None

    def test_progress_out_of_range_400(self, admin_client, app):
        _seed(app)
        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-progress",
            json={"installer_invoice_progress": 101},
        )
        assert resp.status_code == 400

    def test_progress_noop(self, admin_client, app):
        _seed(app)
        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            r.installer_invoice_progress = 10
            db.session.commit()

        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-progress",
            json={"installer_invoice_progress": 10},
        )
        assert resp.status_code == 200
        assert resp.get_json()["changed"] is False
        assert resp.get_json()["event_id"] is None


class TestInstallerInvoiceNumbers:
    def test_set_multiline_numbers(self, admin_client, app):
        _seed(app)
        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-numbers",
            json={"installer_invoice_numbers": "A-100\nB-200"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["installer_invoice_numbers"] == "A-100\nB-200"
        assert body["changed"] is True

        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            assert r.installer_invoice_numbers == "A-100\nB-200"
            events = ReleaseEvents.query.filter_by(
                job=100, release="1", action="update_installer_invoice_numbers"
            ).all()
            assert len(events) == 1
            assert events[0].payload == {"from": None, "to": "A-100\nB-200"}

    def test_clear_numbers_with_empty_string(self, admin_client, app):
        _seed(app)
        admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-numbers",
            json={"installer_invoice_numbers": "INV-9"},
        )
        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-numbers",
            json={"installer_invoice_numbers": "  "},
        )
        assert resp.status_code == 200
        assert resp.get_json()["installer_invoice_numbers"] == ""
        assert resp.get_json()["changed"] is True

        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            assert r.installer_invoice_numbers is None

    def test_numbers_missing_field_400(self, admin_client, app):
        _seed(app)
        resp = admin_client.patch(
            "/brain/subs/releases/100/1/installer-invoice-numbers",
            json={},
        )
        assert resp.status_code == 400


class TestReleaseHubFields:
    """The tab renders Install Prog / Budget and opens the Job Log release hub,
    so the list payload has to carry job_comp, install_hrs, and the raw job-log
    fields JobDetailsBody reads (archived rows never reach /brain/jobs)."""

    def test_list_carries_job_comp_and_install_hrs(self, admin_client, app):
        _seed(app)
        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            r.install_hrs = 12.5
            db.session.commit()

        by_job = {
            row["job"]: row
            for row in admin_client.get("/brain/subs/releases").get_json()["releases"]
        }
        # Install Prog column reads job_comp straight off the Job Log.
        assert by_job[100]["job_comp"] == "X"
        assert by_job[150]["job_comp"] is None
        # Budget column is Install Hrs x $55 client-side.
        assert by_job[100]["install_hrs"] == 12.5
        assert by_job[150]["install_hrs"] is None

    def test_list_carries_release_hub_fields(self, admin_client, app):
        _seed(app)
        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            r.pm = "Bill"
            r.by = "Katie"
            r.num_guys = 3
            r.fab_hrs = 40
            r.paint_color = "Black"
            r.released = date(2026, 5, 1)
            r.ship_date = date(2026, 5, 28)
            r.comp_eta = date(2026, 6, 4)
            r.invoiced = "X"
            r.notes = "watch the embeds"
            r.trello_card_id = "abc123"
            db.session.commit()

        by_job = {
            row["job"]: row
            for row in admin_client.get("/brain/subs/releases").get_json()["releases"]
        }
        row = by_job[100]
        assert row["pm"] == "Bill"
        assert row["by"] == "Katie"
        assert row["num_guys"] == 3
        assert row["fab_hrs"] == 40
        assert row["paint_color"] == "Black"
        assert row["released"] == "2026-05-01"
        assert row["ship_date"] == "2026-05-28"
        assert row["comp_eta"] == "2026-06-04"
        assert row["invoiced"] == "X"
        assert row["notes"] == "watch the embeds"
        assert row["trello_card_id"] == "abc123"
        assert row["stage_group"] == "FABRICATION"
        assert row["fab_order"] == 10

    def test_archived_row_carries_hub_fields_too(self, admin_client, app):
        _seed(app)
        with app.app_context():
            r = Releases.query.filter_by(job=450, release="7").one()
            r.install_hrs = 8
            r.pm = "Bill"
            db.session.commit()

        by_job = {
            row["job"]: row
            for row in admin_client.get("/brain/subs/releases").get_json()["releases"]
        }
        assert by_job[450]["is_archived"] is True
        assert by_job[450]["install_hrs"] == 8
        assert by_job[450]["pm"] == "Bill"

    def test_procore_deep_link_ids_when_viewer_url_present(self, admin_client, app):
        _seed(app)
        with app.app_context():
            r = Releases.query.filter_by(job=100, release="1").one()
            r.procore_submittal_id = "987"
            r.viewer_url = (
                "https://app.procore.com/webclients/host/companies/18521"
                "/projects/55512/tools/submittals/987"
            )
            db.session.commit()

        by_job = {
            row["job"]: row
            for row in admin_client.get("/brain/subs/releases").get_json()["releases"]
        }
        assert by_job[100]["procore_submittal_id"] == "987"
        assert by_job[100]["procore_project_id"] == "55512"
        # No viewer_url -> no deep link, but the keys still exist.
        assert by_job[150]["procore_submittal_id"] is None
        assert by_job[150]["procore_project_id"] is None
