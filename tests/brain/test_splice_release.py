"""Release splicing (T9): 340.1 / 340.2 child releases that carry install hours only.

  - POST /brain/job-log/release/<id>/splice refuses bad input, bad parents, and anonymous callers.
  - The paste / verbal path rejects a free-typed dotted number (how 340.1 slipped in).
"""
import json
from datetime import datetime

from app.models import Releases, db
from tests.conftest import make_release


def _parent(job=340, release="340", install_hrs=150, **extra):
    fields = dict(
        job_name="AMLI - Littleton Village II", description="Balcony rails",
        fab_hrs=200, install_hrs=install_hrs, pm="DP", by="KM", paint_color="Black",
        release_tag="contracted", is_active=True, is_archived=False,
    )
    fields.update(extra)
    return make_release(job, release, "Cut Start", "FABRICATION", 10, **fields)


def _splice(client, parent_id, **body):
    return client.post(f"/brain/job-log/release/{parent_id}/splice", json=body)


class TestCreateSplice:
    def test_archived_parent_and_non_numeric_parent_refused(self, app, non_admin_client):
        with app.app_context():
            a = _parent(is_archived=True); v = _parent(job=341, release="V918")
            db.session.commit(); aid, vid = a.id, v.id
        assert _splice(non_admin_client, aid, install_hrs=5).status_code == 409
        assert _splice(non_admin_client, vid, install_hrs=5).status_code == 409

    def test_requires_login(self, client):
        assert client.post("/brain/job-log/release/1/splice", json={"install_hrs": 5}).status_code == 401
        assert client.get("/brain/job-log/release/1/splices").status_code == 401

    def test_404s_unknown_parent(self, non_admin_client):
        assert _splice(non_admin_client, 999999, install_hrs=5).status_code == 404
        assert non_admin_client.get("/brain/job-log/release/999999/splices").status_code == 404


class TestPastePathRejectsDottedNumbers:
    HEADER = "Job #,Release #,Job,Description,Fab Hrs,Install HRS,Paint color,PM,BY,Released,Fab Order"

    def test_free_typed_splice_number_is_rejected(self, app, non_admin_client):
        with app.app_context():
            _parent(); db.session.commit()
        csv = f"{self.HEADER}\n340,340.1,AMLI - Littleton Village II,Splice,,15,Black,DP,KM,,"
        resp = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": csv, "release_tag": "contracted"},
        )
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["created_count"] == 0
        assert body["error_count"] == 1
        assert "+ Splice" in body["errors"][0]["error"]
        assert "340-340" in body["errors"][0]["error"]
        with app.app_context():
            assert Releases.query.filter_by(release="340.1").count() == 0

    def test_v_numbers_and_plain_numbers_still_pass(self, app, non_admin_client):
        # Different descriptions so the near-duplicate guard doesn't fold them together.
        csv = f"{self.HEADER}\n350,V901,Proj,Rails,10,5,Black,DP,KM,,\n350,902,Proj,Stairs,10,5,Black,DP,KM,,"
        resp = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": csv, "release_tag": "contracted"},
        )
        assert json.loads(resp.data)["created_count"] == 2


class TestSplicedHoursNetOutEverywhere:
    """A splice draws hours OUT of the original's pool, so every view of the original
    shows what it still installs itself — 150 with 50 spliced reads 100. The stored
    install_hrs stays the whole pool (the pool would shrink otherwise)."""

    def _spliced_parent(self, app, client, *, install_hrs=150, budget=50, **extra):
        """Create a 150-hour parent, splice 50 off it, return (parent_id, splice_id)."""
        with app.app_context():
            parent = _parent(install_hrs=install_hrs, **extra)
            db.session.commit()
            parent_id = parent.id
        resp = _splice(
            client, parent_id,
            install_hrs=budget, description="Level 3 balconies only", installer="Saul 1",
        )
        assert resp.status_code == 201, resp.data
        return parent_id, json.loads(resp.data)["splice"]["id"]

    def test_pool_stays_whole_on_the_parent_row(self, app, non_admin_client):
        parent_id, _ = self._spliced_parent(app, non_admin_client)
        with app.app_context():
            assert db.session.get(Releases, parent_id).install_hrs == 150

    def test_job_log_feeds_carry_the_netted_hours(self, app, non_admin_client):
        parent_id, splice_id = self._spliced_parent(app, non_admin_client)
        for url in ("/brain/jobs", "/brain/get-all-jobs"):
            rows = {r["id"]: r for r in json.loads(non_admin_client.get(url).data)["jobs"]}
            parent, splice = rows[parent_id], rows[splice_id]
            assert parent["Install HRS"] == 150, url          # the pool, untouched
            assert parent["spliced_install_hrs"] == 50, url
            assert parent["remaining_install_hrs"] == 100, url
            # The splice carries its own hours; nothing is spliced off IT.
            assert splice["Install HRS"] == 50, url
            assert splice["spliced_install_hrs"] is None, url
            assert splice["remaining_install_hrs"] is None, url

    def test_unspliced_release_is_untouched(self, app, non_admin_client):
        with app.app_context():
            plain = _parent(job=345, release="345", install_hrs=80)
            db.session.commit()
            plain_id = plain.id
        rows = {r["id"]: r for r in json.loads(non_admin_client.get("/brain/jobs").data)["jobs"]}
        assert rows[plain_id]["Install HRS"] == 80
        assert rows[plain_id]["spliced_install_hrs"] is None
        assert rows[plain_id]["remaining_install_hrs"] is None

    def test_second_splice_nets_out_too(self, app, non_admin_client):
        parent_id, _ = self._spliced_parent(app, non_admin_client)
        assert _splice(
            non_admin_client, parent_id,
            install_hrs=25, description="Stair rails, east core", installer="Saul 2",
        ).status_code == 201
        rows = {r["id"]: r for r in json.loads(non_admin_client.get("/brain/jobs").data)["jobs"]}
        assert rows[parent_id]["spliced_install_hrs"] == 75
        assert rows[parent_id]["remaining_install_hrs"] == 75

    def test_additional_hours_never_come_out_of_the_pool(self, app, non_admin_client):
        """Additional hours sit OUTSIDE the pool, so they never shrink what the
        original still installs — only the budget half of a splice does."""
        parent_id, _ = self._spliced_parent(app, non_admin_client)
        resp = _splice(
            non_admin_client, parent_id,
            install_hrs=10, description="Punch list rework", installer="Saul 3",
            additional_install_hrs=20, additional_install_note="Rework after GC redesign",
        )
        assert resp.status_code == 201, resp.data
        rows = {r["id"]: r for r in json.loads(non_admin_client.get("/brain/jobs").data)["jobs"]}
        assert rows[parent_id]["spliced_install_hrs"] == 60      # 50 + 10 budget, not the 20 extra
        assert rows[parent_id]["remaining_install_hrs"] == 90

    def test_splices_summary_carries_group_totals(self, app, non_admin_client):
        """The Splices tab's bar, ledger and subtotal read additional hours and the
        group total from the server, never by adding the splices up client-side."""
        parent_id, _ = self._spliced_parent(app, non_admin_client)
        assert _splice(
            non_admin_client, parent_id,
            install_hrs=10, description="Punch list rework", installer="Saul 3",
            additional_install_hrs=20, additional_install_note="Rework after GC redesign",
        ).status_code == 201
        body = json.loads(non_admin_client.get(f"/brain/job-log/release/{parent_id}/splices").data)
        assert body["total_install_hrs"] == 150
        assert body["allocated_install_hrs"] == 60
        assert body["remaining_install_hrs"] == 90
        assert body["additional_install_hrs"] == 20
        assert body["group_install_hrs"] == 170            # 150 pool + 20 outside it

    def test_splices_summary_totals_without_a_pool(self, app, non_admin_client):
        with app.app_context():
            bare = _parent(job=346, release="346", install_hrs=None)
            db.session.commit()
            bare_id = bare.id
        body = json.loads(non_admin_client.get(f"/brain/job-log/release/{bare_id}/splices").data)
        assert body["total_install_hrs"] is None
        assert body["additional_install_hrs"] == 0
        assert body["group_install_hrs"] is None

    def test_subs_invoice_rows_bill_the_netted_hours(self, app, admin_client):
        parent_id, splice_id = self._spliced_parent(app, admin_client, installer="Saul 1")
        rows = {
            r["id"]: r
            for r in json.loads(admin_client.get("/brain/subs/releases").data)["releases"]
        }
        assert rows[parent_id]["install_hrs"] == 150
        assert rows[parent_id]["remaining_install_hrs"] == 100   # Budget bills 100 x $55, not 150
        assert rows[parent_id]["spliced_install_hrs"] == 50
        assert rows[splice_id]["remaining_install_hrs"] is None

    def test_field_edit_response_carries_the_new_split(self, app, admin_client):
        parent_id, _ = self._spliced_parent(app, admin_client)
        resp = admin_client.patch("/brain/jobs/340/340", json={"fields": {"install_hrs": 200}})
        assert resp.status_code == 200, resp.data
        body = json.loads(resp.data)
        assert body["Install HRS"] == 200
        assert body["remaining_install_hrs"] == 150

    def test_delta_poll_carries_the_parent_when_a_splice_changes(self, app, admin_client):
        """The Job Log polls with ?since=; a splice never touches its parent's row, so
        without this the original keeps showing the gross pool until a full reload."""
        with app.app_context():
            parent = _parent(install_hrs=150, last_updated_at=datetime(2026, 9, 1, 12, 0, 0))
            db.session.commit()
            parent_id = parent.id
            cursor = parent.last_updated_at.isoformat()
        # Nothing has changed since the cursor yet.
        assert json.loads(admin_client.get(f"/brain/jobs?since={cursor}").data)["jobs"] == []

        assert _splice(
            admin_client, parent_id,
            install_hrs=50, description="Level 3 balconies only", installer="Saul 1",
        ).status_code == 201

        rows = {r["id"]: r for r in json.loads(admin_client.get(f"/brain/jobs?since={cursor}").data)["jobs"]}
        assert parent_id in rows, "the original has to come back with the splice"
        assert rows[parent_id]["remaining_install_hrs"] == 100

    def test_deleted_splice_returns_its_hours(self, app, non_admin_client):
        parent_id, splice_id = self._spliced_parent(app, non_admin_client)
        with app.app_context():
            db.session.get(Releases, splice_id).is_active = False
            db.session.commit()
        rows = {r["id"]: r for r in json.loads(non_admin_client.get("/brain/jobs").data)["jobs"]}
        assert rows[parent_id]["spliced_install_hrs"] is None
        assert rows[parent_id]["remaining_install_hrs"] is None
