"""Release splicing (T9): 340.1 / 340.2 child releases that carry install hours only.

  - POST /brain/job-log/release/<id>/splice refuses bad input, bad parents, and anonymous callers.
  - The paste / verbal path rejects a free-typed dotted number (how 340.1 slipped in).
"""
import json

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
