"""T13: the department photo gate, end to end through UpdateStageCommand.

A stage change that crosses FORWARD into the next department (the stage_group
axis: FABRICATION → PAINT → READY_TO_SHIP → COMPLETE) owes a ReleasePhoto tagged
with that department's entry stage, or a written reason. Enforced in the command,
surfaced as 422 photo_required by /brain/update-stage. Helpers are local on
purpose — this file must not lean on fixtures another pass may be reshaping.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.models import ReleaseEvents, ReleasePhoto, Releases, db


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user), \
         patch("app.brain.job_log.routes.get_current_user", return_value=mock_admin_user):
        yield


def _make_release(job, release, **kwargs):
    defaults = dict(
        job=job, release=release, job_name="Test Job",
        stage="Weld Complete", stage_group="FABRICATION", fab_order=10,
    )
    defaults.update(kwargs)
    r = Releases(**defaults)
    db.session.add(r)
    db.session.flush()
    return r


def _add_photo(release_id, stage, *, is_deleted=False):
    p = ReleasePhoto(
        release_id=release_id,
        storage_key=f"{release_id}/x.png",
        mime_type="image/png",
        file_size_bytes=10,
        uploaded_by_user_id=1,
        stage=stage,
        is_deleted=is_deleted,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _patches():
    return (
        patch("app.services.outbox_service.OutboxService.add"),
        patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"),
        patch("app.brain.job_log.routes.get_list_id_by_stage", return_value="list-1"),
    )


def _run(job, release, stage, **kwargs):
    from app.brain.job_log.features.stage.command import UpdateStageCommand
    a, b, c = _patches()
    with a, b, c:
        return UpdateStageCommand(job_id=job, release=release, stage=stage, **kwargs).execute()


def _expect_gate(job, release, stage, *, gate, **kwargs):
    from app.brain.job_log.features.stage.gate import StagePhotoRequiredError
    with pytest.raises(StagePhotoRequiredError) as exc:
        _run(job, release, stage, **kwargs)
    assert exc.value.stage == gate
    assert exc.value.requested_stage == stage
    return exc.value


def _stage_event(job, release):
    return (ReleaseEvents.query
            .filter_by(job=job, release=release, action="update_stage")
            .order_by(ReleaseEvents.id.desc())
            .first())


# ---------------------------------------------------------------------------
# The three department boundaries
# ---------------------------------------------------------------------------

class TestFabToPaint:
    def test_blocked_without_photo(self, app):
        with app.app_context():
            r = _make_release(1, "A")
            db.session.commit()
            _expect_gate(1, "A", "Welded QC", gate="Welded QC")
            db.session.refresh(r)
            assert r.stage == "Weld Complete"

    def test_allowed_with_welded_qc_photo(self, app):
        with app.app_context():
            r = _make_release(1, "A")
            db.session.commit()
            _add_photo(r.id, "Welded QC")
            _run(1, "A", "Welded QC")
            db.session.refresh(r)
            assert r.stage == "Welded QC"
            assert r.stage_group == "PAINT"

    def test_photo_for_a_later_gate_does_not_count(self, app):
        with app.app_context():
            r = _make_release(1, "A")
            db.session.commit()
            _add_photo(r.id, "Paint Complete")
            _expect_gate(1, "A", "Welded QC", gate="Welded QC")


class TestPaintToShip:
    def test_blocked_then_allowed(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Paint Start", stage_group="PAINT")
            db.session.commit()
            _expect_gate(1, "A", "Paint Complete", gate="Paint Complete")
            _add_photo(r.id, "Paint Complete")
            _run(1, "A", "Paint Complete")
            db.session.refresh(r)
            assert r.stage == "Paint Complete"
            assert r.stage_group == "READY_TO_SHIP"


class TestShipToInstall:
    def test_blocked_then_allowed(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Planning", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            _expect_gate(1, "A", "Ship Complete", gate="Ship Complete")
            _add_photo(r.id, "Ship Complete")
            _run(1, "A", "Ship Complete")
            db.session.refresh(r)
            assert r.stage == "Ship Complete"
            assert r.stage_group == "COMPLETE"

    def test_skipping_the_entry_stage_owes_the_same_photo(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Planning", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            err = _expect_gate(1, "A", "Complete", gate="Ship Complete")
            assert err.requested_stage == "Complete"
            _add_photo(r.id, "Ship Complete")
            _run(1, "A", "Complete")
            db.session.refresh(r)
            assert r.stage == "Complete"


# ---------------------------------------------------------------------------
# Moves that never gate
# ---------------------------------------------------------------------------

class TestUngatedMoves:
    def test_inside_paint(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Paint Start", stage_group="PAINT")
            db.session.commit()
            _run(1, "A", "Welded QC")
            db.session.refresh(r)
            assert r.stage == "Welded QC"
            assert r.stage_group == "PAINT"

    def test_inside_ready_to_ship(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Store at MHMW", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            _run(1, "A", "Ship Planning")
            db.session.refresh(r)
            assert r.stage == "Ship Planning"

    def test_backward_with_no_photo(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Complete", stage_group="COMPLETE", fab_order=1)
            db.session.commit()
            _run(1, "A", "Ship Planning")
            db.session.refresh(r)
            assert r.stage == "Ship Planning"
            assert r.stage_group == "READY_TO_SHIP"

    def test_backward_out_of_paint_restores_fabrication(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Welded QC", stage_group="PAINT")
            db.session.commit()
            _run(1, "A", "Weld Complete")
            db.session.refresh(r)
            assert r.stage_group == "FABRICATION"

    def test_undo_bypasses_the_gate(self, app):
        with app.app_context():
            r = _make_release(1, "A")
            db.session.commit()
            _run(1, "A", "Welded QC", undone_event_id=999)
            db.session.refresh(r)
            assert r.stage == "Welded QC"


# ---------------------------------------------------------------------------
# The written-reason exit, and what the event records
# ---------------------------------------------------------------------------

class TestExceptionNote:
    NOTE = "TJ's ship plates, nothing to shoot"

    def test_note_satisfies_the_gate_and_lands_on_the_event(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Planning", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            _run(1, "A", "Ship Complete", gate_exception_note=self.NOTE)
            db.session.refresh(r)
            assert r.stage == "Ship Complete"
            payload = _stage_event(1, "A").payload
            assert payload["gate"] == "Ship Complete"
            assert payload["gate_exception"] == self.NOTE

    def test_photo_satisfied_write_records_gate_only(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Planning", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            _add_photo(r.id, "Ship Complete")
            _run(1, "A", "Ship Complete")
            payload = _stage_event(1, "A").payload
            assert payload["gate"] == "Ship Complete"
            assert "gate_exception" not in payload

    def test_ungated_write_records_neither(self, app):
        with app.app_context():
            _make_release(1, "A", stage="Cut Start")
            db.session.commit()
            _run(1, "A", "Fitup Start")
            payload = _stage_event(1, "A").payload
            assert "gate" not in payload and "gate_exception" not in payload

    def test_whitespace_note_does_not_count(self, app):
        with app.app_context():
            _make_release(1, "A", stage="Ship Planning", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            _expect_gate(1, "A", "Ship Complete", gate="Ship Complete", gate_exception_note="   ")


# ---------------------------------------------------------------------------
# The N5 intercept is checked on the REQUESTED stage
# ---------------------------------------------------------------------------

class TestN5Intercept:
    def _hard_dated_paint_start(self):
        return _make_release(
            1, "A", stage="Paint Start", stage_group="PAINT",
            start_install=date(2026, 10, 5), start_install_formulaTF=False,
        )

    def test_rerouted_paint_complete_still_owes_its_photo(self, app):
        with app.app_context():
            self._hard_dated_paint_start()
            db.session.commit()
            _expect_gate(1, "A", "Paint Complete", gate="Paint Complete")

    def test_with_photo_the_intercept_lands_on_ship_planning(self, app):
        with app.app_context():
            r = self._hard_dated_paint_start()
            db.session.commit()
            _add_photo(r.id, "Paint Complete")
            _run(1, "A", "Paint Complete")
            db.session.refresh(r)
            assert r.stage == "Ship Planning"
            payload = _stage_event(1, "A").payload
            assert payload["via"] == "Paint Complete"
            assert payload["gate"] == "Paint Complete"


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------

class TestRoute:
    def test_422_names_gate_and_requested_stage(self, app):
        with app.app_context():
            _make_release(1, "A", stage="Ship Planning", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            a, b, c = _patches()
            with a, b, c:
                resp = app.test_client().patch("/brain/update-stage/1/A", json={"stage": "Complete"})
            assert resp.status_code == 422, resp.data
            body = resp.get_json()
            assert body["code"] == "photo_required"
            assert body["stage"] == "Ship Complete"
            assert body["requested_stage"] == "Complete"

    def test_note_in_body_passes(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Planning", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()
            a, b, c = _patches()
            with a, b, c:
                resp = app.test_client().patch(
                    "/brain/update-stage/1/A",
                    json={"stage": "Complete", "gate_exception_note": "delivered by the GC's crane crew"},
                )
            assert resp.status_code == 200, resp.data
            db.session.refresh(r)
            assert r.stage == "Complete"


# ---------------------------------------------------------------------------
# The two PAINT consumers that had to move with the split
# ---------------------------------------------------------------------------

class TestPaintConsumers:
    @pytest.mark.parametrize("old_group", ["FABRICATION", "COMPLETE"])
    def test_welded_qc_handoff_retiers_from_outside_the_booth(self, app, old_group):
        from app.brain.job_log.features.fab_order.tier import plan_fab_order_for_stage
        with app.app_context():
            _make_release(2, "B", stage="Paint Start", stage_group="PAINT", fab_order=9)
            r = _make_release(1, "A", stage="Weld Complete", fab_order=20)
            db.session.flush()
            plan = plan_fab_order_for_stage(r, "Welded QC", old_group)
            assert plan is not None and plan.fab_order == 10

    @pytest.mark.parametrize("old_group", ["PAINT", "READY_TO_SHIP"])
    def test_welded_qc_from_inside_the_shop_keeps_its_position(self, app, old_group):
        from app.brain.job_log.features.fab_order.tier import plan_fab_order_for_stage
        with app.app_context():
            _make_release(2, "B", stage="Paint Start", stage_group="PAINT", fab_order=9)
            r = _make_release(1, "A", stage="Paint Start", stage_group="PAINT", fab_order=12)
            db.session.flush()
            assert plan_fab_order_for_stage(r, "Welded QC", old_group) is None

    def test_installer_timeline_includes_paint_rows(self, app):
        with app.app_context():
            _make_release(
                560, "923", stage="Welded QC", stage_group="PAINT",
                start_install=date(2026, 10, 5), start_install_formulaTF=False,
                install_hrs=16.0,
            )
            db.session.commit()
            resp = app.test_client().get("/brain/gantt-data")
            assert resp.status_code == 200, resp.data
            releases = [rel for p in resp.get_json()["projects"] for rel in p["releases"]]
            assert any(rel["job"] == 560 and rel["release"] == "923" for rel in releases)
