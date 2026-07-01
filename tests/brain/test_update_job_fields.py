"""Tests for the bulk Job Log row-field update endpoint.

PATCH /brain/jobs/<job>/<release> accepts {"fields": {...}} and applies every
field in one commit + one ReleaseEvents row, rejecting the whole request (no
partial write) if any field is invalid.
"""
from app.models import Releases, ReleaseEvents, db
from tests.conftest import make_release

# Shared fixtures (app, client, mock_admin_user, mock_non_admin_user) live in
# tests/conftest.py. admin_client / non_admin_client live in tests/brain/conftest.py.


class TestUpdateJobFields:
    def test_multiple_fields_update_together_in_one_request(self, app, admin_client):
        with app.app_context():
            make_release(1, "A", fab_hrs=10, install_hrs=5, pm="Old PM")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/jobs/1/A",
                json={"fields": {"fab_hrs": 12.5, "install_hrs": 8, "pm": "New PM"}},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r = Releases.query.filter_by(job=1, release="A").first()
            assert r.fab_hrs == 12.5
            assert r.install_hrs == 8
            assert r.pm == "New PM"

            evs = ReleaseEvents.query.filter_by(job=1, release="A", action="updated").all()
            assert len(evs) == 1
            assert set(evs[0].payload.keys()) == {"fab_hrs", "install_hrs", "pm"}
            assert evs[0].payload["pm"] == {"old_value": "Old PM", "new_value": "New PM"}

    def test_invalid_field_rejects_whole_request(self, app, admin_client):
        with app.app_context():
            make_release(2, "A", fab_hrs=10, pm="Old PM")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/jobs/2/A",
                json={"fields": {"pm": "New PM", "not_a_real_field": "x"}},
            )
            assert resp.status_code == 400

            db.session.expire_all()
            r = Releases.query.filter_by(job=2, release="A").first()
            assert r.pm == "Old PM"
            assert not ReleaseEvents.query.filter_by(job=2, release="A").all()

    def test_invalid_value_rejects_whole_request(self, app, admin_client):
        with app.app_context():
            make_release(3, "A", fab_hrs=10, install_hrs=5)
            db.session.commit()

            resp = admin_client.patch(
                "/brain/jobs/3/A",
                json={"fields": {"fab_hrs": 12, "install_hrs": "not-a-number"}},
            )
            assert resp.status_code == 400

            db.session.expire_all()
            r = Releases.query.filter_by(job=3, release="A").first()
            assert r.fab_hrs == 10
            assert r.install_hrs == 5

    def test_non_admin_forbidden(self, app, non_admin_client):
        with app.app_context():
            make_release(4, "A")
            db.session.commit()

            resp = non_admin_client.patch(
                "/brain/jobs/4/A",
                json={"fields": {"pm": "New PM"}},
            )
            assert resp.status_code == 403
