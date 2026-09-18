"""Release splicing (T9): 340.1 / 340.2 child releases that carry install hours only.

  - POST /brain/job-log/release/<id>/splice refuses bad input, bad parents, and anonymous callers.
  - The paste / verbal path rejects a free-typed dotted number (how 340.1 slipped in).
  - Creating a splice: derived numbering (never re-issued), required scope + installer, the pool
    cap, additional hours outside it, no fab hours, no Trello.
  - The field-edit PATCH keeps numbers derived and the pool honest (validate_field_edits).
  - PATCH .../splice/additional-hours moves a splice's hours outside the pool, reason kept.
  - Job Log + Subs rows carry what the two-line hours cell reads (parent_install_hrs & co).
"""
import json
from datetime import datetime

from app.models import Releases, TrelloOutbox, db
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


def _make_parent(app, **kw):
    with app.app_context():
        parent = _parent(**kw)
        db.session.commit()
        return parent.id


def _ok_splice(client, parent_id, **body):
    """A valid create; the caller overrides what it is testing."""
    fields = dict(install_hrs=50, description="Level 3 balconies only", installer="Saul 1")
    fields.update(body)
    return _splice(client, parent_id, **fields)


def _body(resp):
    return json.loads(resp.data)


class TestCreateSpliceRules:

    def test_creates_the_next_numbered_splice_with_install_hours_only(self, app, non_admin_client):
        parent_id = _make_parent(app)
        resp = _ok_splice(non_admin_client, parent_id, stage="Weld Start", start_install="2026-10-05")
        assert resp.status_code == 201, resp.data
        splice = _body(resp)["splice"]
        assert splice["release"] == "340.1"
        assert splice["parent_release_id"] == parent_id
        assert splice["install_hrs"] == 50
        assert splice["installer"] == "Saul 1"
        assert splice["stage"] == "Weld Start"
        assert splice["start_install"] == "2026-10-05"
        with app.app_context():
            row = db.session.get(Releases, splice["id"])
            assert row.fab_hrs is None
            assert row.comp_eta is not None               # hard start date -> comp_eta computed
            assert TrelloOutbox.query.count() == 0        # splices never touch Trello
        assert _body(_ok_splice(non_admin_client, parent_id, install_hrs=10))["splice"]["release"] == "340.2"

    def test_a_dead_splices_number_is_never_reissued(self, app, non_admin_client):
        parent_id = _make_parent(app)
        first = _body(_ok_splice(non_admin_client, parent_id))["splice"]["id"]
        with app.app_context():
            db.session.get(Releases, first).is_archived = True
            db.session.commit()
        assert _body(_ok_splice(non_admin_client, parent_id))["splice"]["release"] == "340.2"

    def test_description_is_required_and_must_differ_from_the_original(self, app, non_admin_client):
        parent_id = _make_parent(app)
        assert _ok_splice(non_admin_client, parent_id, description="  ").status_code == 400
        # Case and whitespace do not make it different.
        resp = _ok_splice(non_admin_client, parent_id, description="  balcony   RAILS ")
        assert resp.status_code == 400
        assert "differ" in _body(resp)["error"]

    def test_installer_is_required(self, app, non_admin_client):
        parent_id = _make_parent(app)
        assert _ok_splice(non_admin_client, parent_id, installer="").status_code == 400

    def test_unknown_stage_is_refused(self, app, non_admin_client):
        parent_id = _make_parent(app)
        assert _ok_splice(non_admin_client, parent_id, stage="Teleported").status_code == 400

    def test_budget_hours_are_capped_by_what_is_left_in_the_pool(self, app, non_admin_client):
        parent_id = _make_parent(app, install_hrs=150)
        assert _ok_splice(non_admin_client, parent_id, install_hrs=100).status_code == 201
        resp = _ok_splice(non_admin_client, parent_id, install_hrs=51)
        assert resp.status_code == 409
        assert _body(resp)["remaining_install_hrs"] == 50
        # Exactly what is left is fine.
        assert _ok_splice(non_admin_client, parent_id, install_hrs=50).status_code == 201

    def test_budget_hours_need_a_pool(self, app, non_admin_client):
        parent_id = _make_parent(app, install_hrs=None)
        assert _ok_splice(non_admin_client, parent_id).status_code == 409

    def test_additional_hours_need_a_reason(self, app, non_admin_client):
        parent_id = _make_parent(app)
        resp = _ok_splice(non_admin_client, parent_id, install_hrs=0, additional_install_hrs=14)
        assert resp.status_code == 400

    def test_additional_only_splice_sits_outside_the_pool(self, app, non_admin_client):
        parent_id = _make_parent(app, install_hrs=12)
        assert _ok_splice(non_admin_client, parent_id, install_hrs=12).status_code == 201   # pool drained
        resp = _ok_splice(
            non_admin_client, parent_id,
            install_hrs=0, additional_install_hrs=14, additional_install_note="Extra scope",
        )
        assert resp.status_code == 201, resp.data
        splice = _body(resp)["splice"]
        assert splice["install_hrs"] == 14
        assert splice["additional_install_hrs"] == 14
        assert splice["additional_install_note"] == "Extra scope"

    def test_a_splice_needs_some_hours(self, app, non_admin_client):
        parent_id = _make_parent(app)
        assert _ok_splice(non_admin_client, parent_id, install_hrs=0).status_code == 400

    def test_a_splice_cannot_be_spliced(self, app, non_admin_client):
        parent_id = _make_parent(app)
        splice_id = _body(_ok_splice(non_admin_client, parent_id))["splice"]["id"]
        resp = _ok_splice(non_admin_client, splice_id, description="Splice of a splice", install_hrs=5)
        assert resp.status_code == 409


class TestFieldEditGuards:
    """PATCH /brain/jobs/<job>/<release> — numbers stay derived, the pool stays honest."""

    @staticmethod
    def _patch(client, row, **fields):
        return client.patch(f"/brain/jobs/340/{row}", json={"fields": fields})

    def _group(self, app, client, **splice_body):
        parent_id = _make_parent(app, install_hrs=150)
        splice = _body(_ok_splice(client, parent_id, **splice_body))["splice"]
        return parent_id, splice

    def test_a_splices_number_cannot_be_edited(self, app, admin_client):
        self._group(app, admin_client)
        assert self._patch(admin_client, "340.1", release="340.7").status_code == 400

    def test_a_dotted_number_cannot_be_typed_onto_a_release(self, app, admin_client):
        _make_parent(app)
        assert self._patch(admin_client, "340", release="340.1").status_code == 400

    def test_the_original_cannot_be_renumbered_while_splices_exist(self, app, admin_client):
        self._group(app, admin_client)
        assert self._patch(admin_client, "340", release="341").status_code == 409

    def test_job_number_is_locked_across_the_group(self, app, admin_client):
        self._group(app, admin_client)
        assert self._patch(admin_client, "340", job=341).status_code == 409
        assert self._patch(admin_client, "340.1", job=341).status_code == 409

    def test_a_splice_never_carries_fab_hours(self, app, admin_client):
        self._group(app, admin_client)
        assert self._patch(admin_client, "340.1", fab_hrs=5).status_code == 400

    def test_a_splices_install_hours_stay_inside_the_pool(self, app, admin_client):
        self._group(app, admin_client)                                     # 50 of 150 drawn
        assert self._patch(admin_client, "340.1", install_hrs=151).status_code == 409
        assert self._patch(admin_client, "340.1", install_hrs=150).status_code == 200

    def test_a_splices_install_hours_cannot_drop_below_its_additional(self, app, admin_client):
        self._group(
            app, admin_client,
            install_hrs=10, additional_install_hrs=8, additional_install_note="Rework",
        )
        assert self._patch(admin_client, "340.1", install_hrs=5).status_code == 409

    def test_the_originals_pool_cannot_drop_below_what_is_spliced(self, app, admin_client):
        self._group(app, admin_client)                                     # 50 spliced off
        assert self._patch(admin_client, "340", install_hrs=40).status_code == 409
        assert self._patch(admin_client, "340", install_hrs=50).status_code == 200


class TestAdditionalHoursPatch:

    @staticmethod
    def _patch(client, release_id, **body):
        return client.patch(f"/brain/job-log/release/{release_id}/splice/additional-hours", json=body)

    def test_adds_hours_outside_the_pool_with_a_reason(self, app, non_admin_client):
        parent_id = _make_parent(app)
        splice_id = _body(_ok_splice(non_admin_client, parent_id))["splice"]["id"]
        assert self._patch(non_admin_client, splice_id, additional_install_hrs=6).status_code == 400
        resp = self._patch(
            non_admin_client, splice_id, additional_install_hrs=6, additional_install_note="GC added a run",
        )
        assert resp.status_code == 200, resp.data
        body = _body(resp)
        assert body["splice"]["install_hrs"] == 56                  # budget 50 + 6
        assert body["pool"]["allocated_install_hrs"] == 50          # the pool is untouched
        assert body["pool"]["additional_install_hrs"] == 6

    def test_keeps_the_recorded_reason_and_clears_to_zero(self, app, non_admin_client):
        parent_id = _make_parent(app)
        splice_id = _body(_ok_splice(
            non_admin_client, parent_id, additional_install_hrs=4, additional_install_note="Original reason",
        ))["splice"]["id"]
        resp = self._patch(
            non_admin_client, splice_id, additional_install_hrs=9, additional_install_note="Ignored",
        )
        assert _body(resp)["splice"]["additional_install_note"] == "Original reason"
        assert _body(resp)["splice"]["install_hrs"] == 59
        resp = self._patch(non_admin_client, splice_id, additional_install_hrs=0)
        assert resp.status_code == 200
        assert _body(resp)["splice"]["additional_install_hrs"] is None
        assert _body(resp)["splice"]["install_hrs"] == 50
        assert _body(resp)["splice"]["additional_install_note"] == "Original reason"

    def test_refuses_negative_hours_and_non_splices(self, app, non_admin_client):
        parent_id = _make_parent(app)
        splice_id = _body(_ok_splice(non_admin_client, parent_id))["splice"]["id"]
        assert self._patch(non_admin_client, splice_id, additional_install_hrs=-1).status_code == 400
        assert self._patch(
            non_admin_client, parent_id, additional_install_hrs=3, additional_install_note="x",
        ).status_code == 409
        assert self._patch(non_admin_client, 999999, additional_install_hrs=3).status_code == 404


class TestHoursCellFields:
    """What the Job Log / Invoice Paid two-line hours cell reads off each row."""

    def _group(self, app, client, installer="Saul 1"):
        parent_id = _make_parent(app, install_hrs=12, installer=installer)
        budget = _body(_ok_splice(client, parent_id, install_hrs=10))["splice"]["id"]
        extra = _body(_ok_splice(
            client, parent_id, install_hrs=0, description="Extra budget",
            additional_install_hrs=14, additional_install_note="Test",
        ))["splice"]["id"]
        with app.app_context():
            other = _parent(job=615, release="551", install_hrs=26)
            db.session.commit()
            other_id = other.id
        return parent_id, budget, extra, other_id

    def test_job_log_splice_rows_carry_their_groups_pool(self, app, non_admin_client):
        parent_id, budget, extra, other_id = self._group(app, non_admin_client)
        for url in ("/brain/jobs", "/brain/get-all-jobs"):
            rows = {r["id"]: r for r in _body(non_admin_client.get(url))["jobs"]}
            assert rows[budget]["parent_install_hrs"] == 12, url
            assert rows[extra]["parent_install_hrs"] == 12, url
            assert rows[extra]["additional_install_hrs"] == 14, url
            assert rows[parent_id]["parent_install_hrs"] is None, url    # not a splice
            assert rows[other_id]["parent_install_hrs"] is None, url

    def test_subs_rows_carry_the_same_fields(self, app, admin_client):
        parent_id, budget, extra, other_id = self._group(app, admin_client)
        rows = {r["id"]: r for r in _body(admin_client.get("/brain/subs/releases"))["releases"]}
        assert rows[budget]["parent_release_id"] == parent_id
        assert rows[budget]["parent_install_hrs"] == 12
        assert rows[extra]["additional_install_hrs"] == 14
        assert rows[extra]["additional_install_note"] == "Test"
        assert rows[parent_id]["parent_release_id"] is None
        assert rows[parent_id]["parent_install_hrs"] is None
