"""Tests for the bulk Job Log row-field update endpoint.

PATCH /brain/jobs/<job>/<release> accepts {"fields": {...}} and applies every
field in one commit + one ReleaseEvents row, rejecting the whole request (no
partial write) if any field is invalid.
"""
from unittest.mock import patch

from app.models import Releases, ReleaseEvents, TrelloOutbox, db
from app.services.outbox_service import OutboxService
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

    def test_plain_user_forbidden(self, app, non_admin_client):
        """Neither admin nor drafter → 403."""
        with app.app_context():
            make_release(4, "A")
            db.session.commit()

            resp = non_admin_client.patch(
                "/brain/jobs/4/A",
                json={"fields": {"pm": "New PM"}},
            )
            assert resp.status_code == 403

    def test_drafter_can_edit_job_through_released_fields(self, app, drafter_client):
        """DP: drafters may PATCH the job→released block via the gear modal."""
        with app.app_context():
            make_release(
                40, "A",
                job_name="Old Name",
                description="Old desc",
                fab_hrs=10,
                install_hrs=5,
                paint_color="Red",
                pm="Old PM",
                by="Old BY",
            )
            db.session.commit()

            resp = drafter_client.patch(
                "/brain/jobs/40/A",
                json={
                    "fields": {
                        "job_name": "Columbine Square",
                        "description": "RFI angles",
                        "fab_hrs": 12,
                        "install_hrs": 8,
                        "paint_color": "Prime",
                        "pm": "RL",
                        "by": "DCR",
                        "released": "2026-08-05",
                    }
                },
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r = Releases.query.filter_by(job=40, release="A").first()
            assert r.job_name == "Columbine Square"
            assert r.description == "RFI angles"
            assert r.fab_hrs == 12
            assert r.install_hrs == 8
            assert r.paint_color == "Prime"
            assert r.pm == "RL"
            assert r.by == "DCR"
            assert str(r.released) == "2026-08-05"
            assert r.source_of_update == "Brain"

            ev = ReleaseEvents.query.filter_by(job=40, release="A", action="updated").first()
            assert ev is not None

    def test_drafter_cannot_delete_row(self, app, drafter_client):
        """Delete stays admin-only; drafters only get field edit."""
        with app.app_context():
            make_release(41, "A")
            db.session.commit()

            resp = drafter_client.delete("/brain/jobs/41/A")
            assert resp.status_code == 403
            assert Releases.query.filter_by(job=41, release="A").first().is_active is not False

    def test_queues_trello_sync_when_card_linked(self, app, admin_client):
        with app.app_context():
            make_release(5, "A", pm="Old PM", trello_card_id="card-555")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/jobs/5/A",
                json={"fields": {"pm": "New PM"}},
            )
            assert resp.status_code == 200

            ev = ReleaseEvents.query.filter_by(job=5, release="A", action="updated").first()
            assert ev.applied_at is None  # left open for the outbox to close

            outbox_items = TrelloOutbox.query.filter_by(event_id=ev.id).all()
            assert len(outbox_items) == 1
            assert outbox_items[0].destination == "trello"
            assert outbox_items[0].action == "update_release_fields"
            assert outbox_items[0].status == "pending"

    def test_no_trello_sync_queued_without_card(self, app, admin_client):
        with app.app_context():
            make_release(6, "A", pm="Old PM", trello_card_id=None)
            db.session.commit()

            resp = admin_client.patch(
                "/brain/jobs/6/A",
                json={"fields": {"pm": "New PM"}},
            )
            assert resp.status_code == 200

            ev = ReleaseEvents.query.filter_by(job=6, release="A", action="updated").first()
            assert ev.applied_at is not None  # closed immediately, no card to sync to
            assert not TrelloOutbox.query.filter_by(event_id=ev.id).all()

    def test_renaming_release_keeps_outbox_lookup_working(self, app, admin_client):
        """Regression: renaming release in the same request as other fields used
        to key the event on the pre-edit (job, release), so the outbox worker's
        lookup by that identity missed the row (it now lives under the new
        release) and the Trello sync failed permanently with "not found"."""
        with app.app_context():
            make_release(7, "A", pm="Old PM", trello_card_id="card-777", mirror_trello_card_id="mirror-777")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/jobs/7/A",
                json={"fields": {"release": "B", "pm": "New PM"}},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            assert Releases.query.filter_by(job=7, release="A").first() is None
            renamed = Releases.query.filter_by(job=7, release="B").first()
            assert renamed is not None

            # The event — and the outbox item's lookup key — must reflect the
            # NEW (post-rename) identity, not the pre-edit URL params.
            ev = ReleaseEvents.query.filter_by(job=7, release="B", action="updated").first()
            assert ev is not None
            assert not ReleaseEvents.query.filter_by(job=7, release="A").all()

            item = TrelloOutbox.query.filter_by(event_id=ev.id).first()
            assert item is not None

            with patch("app.trello.api.update_trello_card_name") as mock_name, \
                 patch("app.trello.api.update_trello_card_description") as mock_desc:
                assert OutboxService.process_item(item) is True

            # release is embedded in the title, so it must be regenerated too
            # (and mirrored onto the linked mirror card).
            assert mock_name.call_args_list[0].args == ("card-777", "7-B Test Job Unknown Description")
            assert mock_name.call_args_list[1].args == ("mirror-777", "7-B Test Job Unknown Description")
            assert mock_desc.call_count == 2

            db.session.refresh(item)
            assert item.status == "completed"
