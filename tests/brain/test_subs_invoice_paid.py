"""Tests for the admin Subs installer-invoice-paid page API."""
from datetime import date

import pytest

from app.models import Releases, ReleaseEvents, db
from tests.conftest import make_release


def _seed(app):
    """Three assigned active rows, one unassigned, one archived, one inactive."""
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
        # Should be excluded: archived
        make_release(
            400, "1", job_name="Archived",
            installer="Oscar", is_active=True, is_archived=True,
        )
        # Should be excluded: inactive
        make_release(
            500, "1", job_name="Inactive",
            installer="Oscar", is_active=False, is_archived=False,
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
        # Only the three active assigned rows
        assert len(releases) == 3
        keys = [(r["installer"], r["job"], r["release"]) for r in releases]
        assert keys == [
            ("Octavio", 150, "3"),
            ("Octavio", 200, "2"),
            ("Saul 2", 100, "1"),
        ]
        assert data["installers"] == ["Octavio", "Saul 2"]
        # Paid flag preserved
        by_job = {r["job"]: r for r in releases}
        assert by_job[200]["installer_invoice_paid"] is True
        assert by_job[100]["installer_invoice_paid"] is False

    def test_paid_filter(self, admin_client, app):
        _seed(app)
        unpaid = admin_client.get("/brain/subs/releases?paid=false").get_json()["releases"]
        paid = admin_client.get("/brain/subs/releases?paid=true").get_json()["releases"]
        assert {r["job"] for r in unpaid} == {100, 150}
        assert {r["job"] for r in paid} == {200}

    def test_installer_filter(self, admin_client, app):
        _seed(app)
        data = admin_client.get("/brain/subs/releases?installer=Octavio").get_json()
        assert {r["job"] for r in data["releases"]} == {150, 200}
        # installers roster stays full so the dropdown doesn't collapse
        assert data["installers"] == ["Octavio", "Saul 2"]


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
