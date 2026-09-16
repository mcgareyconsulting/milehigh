"""Release splicing (T9): 340.1 / 340.2 child releases that carry install hours only.

  - POST /brain/job-log/release/<id>/splice derives the number, draws install
    hours from the parent's pool, carries no fab hours, queues nothing to Trello.
  - GET  /brain/job-log/release/<id>/splices reports the pool from either side.
  - The paste / verbal path rejects a free-typed dotted number (how 340.1 slipped in).
  - PATCH field edits can't break the link or over-allocate the pool.
"""
import json

from app.models import Releases, ReleaseEvents, TrelloOutbox, db
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
    def test_derives_number_copies_parent_and_draws_from_pool(self, app, non_admin_client):
        with app.app_context():
            p = _parent(); db.session.commit(); pid = p.id

        resp = _splice(non_admin_client, pid, install_hrs=15)
        assert resp.status_code == 201, resp.data
        body = json.loads(resp.data)
        assert body["splice"]["release"] == "340.1"
        assert body["pool"]["remaining_install_hrs"] == 135
        assert body["pool"]["next_splice_number"] == "340.2"

        with app.app_context():
            s = Releases.query.filter_by(job=340, release="340.1").one()
            assert s.parent_release_id == pid
            assert s.install_hrs == 15
            assert s.fab_hrs is None
            assert s.job_name == "AMLI - Littleton Village II"
            assert s.description == "Balcony rails"  # inherited when blank
            assert s.pm == "DP" and s.by == "KM" and s.paint_color == "Black"
            assert s.release_tag == "contracted"
            assert s.stage == "Released"
            assert s.trello_card_id is None
            # Parent's total is untouched — it IS the pool.
            assert Releases.query.get(pid).install_hrs == 150
            ev = ReleaseEvents.query.filter_by(job=340, release="340.1", action="created").one()
            assert ev.payload["splice"] is True
            assert ev.payload["parent_release_id"] == pid
            assert ev.payload["Fab Hrs"] is None
            # Zero Trello interaction.
            assert TrelloOutbox.query.count() == 0

    def test_numbers_climb_and_description_is_editable(self, app, non_admin_client):
        with app.app_context():
            p = _parent(); db.session.commit(); pid = p.id
        assert _splice(non_admin_client, pid, install_hrs=15).status_code == 201
        resp = _splice(non_admin_client, pid, install_hrs=10, description="Wall handrails only", released="2026-10-01")
        assert resp.status_code == 201
        body = json.loads(resp.data)
        assert body["splice"]["release"] == "340.2"
        assert body["splice"]["description"] == "Wall handrails only"
        assert body["splice"]["released"] == "2026-10-01"
        assert body["pool"]["allocated_install_hrs"] == 25
        assert body["pool"]["remaining_install_hrs"] == 125

    def test_pool_cannot_be_exceeded(self, app, non_admin_client):
        with app.app_context():
            p = _parent(install_hrs=20); db.session.commit(); pid = p.id
        assert _splice(non_admin_client, pid, install_hrs=15).status_code == 201
        resp = _splice(non_admin_client, pid, install_hrs=10)
        assert resp.status_code == 409
        body = json.loads(resp.data)
        assert body["remaining_install_hrs"] == 5
        assert "5 of 20" in body["error"]
        with app.app_context():
            assert Releases.query.filter_by(job=340, release="340.2").count() == 0

    def test_exactly_the_remainder_is_allowed(self, app, non_admin_client):
        with app.app_context():
            p = _parent(install_hrs=20); db.session.commit(); pid = p.id
        assert _splice(non_admin_client, pid, install_hrs=15).status_code == 201
        assert _splice(non_admin_client, pid, install_hrs=5).status_code == 201

    def test_parent_without_install_hours_cannot_splice(self, app, non_admin_client):
        with app.app_context():
            p = _parent(install_hrs=None); db.session.commit(); pid = p.id
        resp = _splice(non_admin_client, pid, install_hrs=5)
        assert resp.status_code == 409
        assert "install hours" in json.loads(resp.data)["error"].lower()

    def test_install_hours_required_and_positive(self, app, non_admin_client):
        with app.app_context():
            p = _parent(); db.session.commit(); pid = p.id
        assert _splice(non_admin_client, pid, install_hrs=0).status_code == 400
        assert _splice(non_admin_client, pid, install_hrs="abc").status_code == 400
        assert non_admin_client.post(f"/brain/job-log/release/{pid}/splice", json={}).status_code == 400

    def test_cannot_splice_a_splice(self, app, non_admin_client):
        with app.app_context():
            p = _parent(); db.session.commit(); pid = p.id
        first = json.loads(_splice(non_admin_client, pid, install_hrs=15).data)["splice"]["id"]
        resp = _splice(non_admin_client, first, install_hrs=5)
        assert resp.status_code == 409
        assert "itself a splice" in json.loads(resp.data)["error"]

    def test_archived_parent_and_non_numeric_parent_refused(self, app, non_admin_client):
        with app.app_context():
            a = _parent(is_archived=True); v = _parent(job=341, release="V918")
            db.session.commit(); aid, vid = a.id, v.id
        assert _splice(non_admin_client, aid, install_hrs=5).status_code == 409
        assert _splice(non_admin_client, vid, install_hrs=5).status_code == 409

    def test_dead_splice_numbers_are_never_reissued(self, app, non_admin_client):
        with app.app_context():
            p = _parent(); db.session.commit(); pid = p.id
        sid = json.loads(_splice(non_admin_client, pid, install_hrs=15).data)["splice"]["id"]
        with app.app_context():
            s = Releases.query.get(sid); s.is_active = False; db.session.commit()
        body = json.loads(_splice(non_admin_client, pid, install_hrs=15).data)
        assert body["splice"]["release"] == "340.2"
        # ...and the deleted splice's hours are released back to the pool.
        assert body["pool"]["allocated_install_hrs"] == 15

    def test_requires_login(self, client):
        assert client.post("/brain/job-log/release/1/splice", json={"install_hrs": 5}).status_code == 401
        assert client.get("/brain/job-log/release/1/splices").status_code == 401

    def test_404s_unknown_parent(self, non_admin_client):
        assert _splice(non_admin_client, 999999, install_hrs=5).status_code == 404
        assert non_admin_client.get("/brain/job-log/release/999999/splices").status_code == 404


class TestSplicesEndpoint:
    def test_reads_the_same_pool_from_parent_or_child(self, app, non_admin_client):
        with app.app_context():
            p = _parent(); db.session.commit(); pid = p.id
        sid = json.loads(_splice(non_admin_client, pid, install_hrs=15).data)["splice"]["id"]

        from_parent = json.loads(non_admin_client.get(f"/brain/job-log/release/{pid}/splices").data)
        from_child = json.loads(non_admin_client.get(f"/brain/job-log/release/{sid}/splices").data)
        assert from_parent["is_splice"] is False and from_child["is_splice"] is True
        for body in (from_parent, from_child):
            assert body["parent_id"] == pid
            assert body["total_install_hrs"] == 150
            assert body["remaining_install_hrs"] == 135
            assert [s["release"] for s in body["splices"]] == ["340.1"]

    def test_job_list_exposes_parent_release_id(self, app, non_admin_client):
        with app.app_context():
            p = _parent(); db.session.commit(); pid = p.id
        _splice(non_admin_client, pid, install_hrs=15)
        rows = json.loads(non_admin_client.get("/brain/jobs?limit=50").data)
        rows = rows if isinstance(rows, list) else rows.get("jobs") or rows.get("data")
        by_release = {r["Release #"]: r for r in rows}
        assert by_release["340"]["parent_release_id"] is None
        assert by_release["340.1"]["parent_release_id"] == pid


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


class TestFieldEditGuards:
    def _setup(self, app, client, parent_hrs=150, first=15):
        with app.app_context():
            p = _parent(install_hrs=parent_hrs); db.session.commit(); pid = p.id
        sid = json.loads(_splice(client, pid, install_hrs=first).data)["splice"]["id"]
        return pid, sid

    def test_splice_cannot_take_fab_hours(self, app, admin_client):
        self._setup(app, admin_client)
        resp = admin_client.patch("/brain/jobs/340/340.1", json={"fields": {"fab_hrs": 5}})
        assert resp.status_code == 400
        # Clearing / zero is fine.
        assert admin_client.patch("/brain/jobs/340/340.1", json={"fields": {"fab_hrs": 0}}).status_code == 200

    def test_splice_install_hours_edit_respects_pool(self, app, admin_client):
        self._setup(app, admin_client, parent_hrs=20, first=15)
        # Own 15 re-enters the pool: up to 20 is fine, 21 is not.
        assert admin_client.patch("/brain/jobs/340/340.1", json={"fields": {"install_hrs": 20}}).status_code == 200
        resp = admin_client.patch("/brain/jobs/340/340.1", json={"fields": {"install_hrs": 21}})
        assert resp.status_code == 409
        assert admin_client.patch("/brain/jobs/340/340.1", json={"fields": {"install_hrs": 0}}).status_code == 400

    def test_parent_total_cannot_drop_below_allocated(self, app, admin_client):
        self._setup(app, admin_client, parent_hrs=150, first=15)
        assert admin_client.patch("/brain/jobs/340/340", json={"fields": {"install_hrs": 15}}).status_code == 200
        resp = admin_client.patch("/brain/jobs/340/340", json={"fields": {"install_hrs": 14}})
        assert resp.status_code == 409
        assert "already spliced" in json.loads(resp.data)["error"]

    def test_release_numbers_stay_linked(self, app, admin_client):
        self._setup(app, admin_client)
        # A splice's number is derived.
        assert admin_client.patch("/brain/jobs/340/340.1", json={"fields": {"release": "999"}}).status_code == 400
        # A parent with splices can't be renumbered out from under them.
        assert admin_client.patch("/brain/jobs/340/340", json={"fields": {"release": "341"}}).status_code == 409
        # Nobody can rename an ordinary release into a dotted number.
        with app.app_context():
            make_release(360, "360", job_name="Other"); db.session.commit()
        assert admin_client.patch("/brain/jobs/360/360", json={"fields": {"release": "360.1"}}).status_code == 400
        # Ordinary edits on either side still work.
        assert admin_client.patch("/brain/jobs/340/340.1", json={"fields": {"description": "Floor 1 only"}}).status_code == 200
