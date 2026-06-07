"""Tests for the stage-change photo gate.

Moving a release into "Welded QC" or "Paint Complete" requires a non-deleted
ReleasePhoto tagged with that exact stage. The gate is enforced in
UpdateStageCommand and surfaced as HTTP 422 (code=photo_required) by the
/brain/update-stage route.
"""
import pytest
from unittest.mock import patch

from app.models import Releases, ReleasePhoto, db


@pytest.fixture(autouse=True)
def _enable_stage_photo_gate():
    # The gate ships disabled (STAGE_PHOTO_GATE_ENABLED=False). These tests
    # verify the gate infrastructure works when the flag is flipped on.
    with patch("app.brain.job_log.features.stage.command.STAGE_PHOTO_GATE_ENABLED", True):
        yield


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
    return [
        patch("app.services.outbox_service.OutboxService.add"),
        patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"),
    ]


# ---------------------------------------------------------------------------
# Command-level gate
# ---------------------------------------------------------------------------


def test_welded_qc_without_photo_raises(app):
    with app.app_context():
        r = _make_release(1, "A")
        db.session.commit()

        from app.brain.job_log.features.stage.command import (
            UpdateStageCommand, StagePhotoRequiredError,
        )
        p = _patches()
        with p[0], p[1]:
            with pytest.raises(StagePhotoRequiredError) as exc:
                UpdateStageCommand(job_id=1, release="A", stage="Welded QC").execute()
        assert exc.value.stage == "Welded QC"

        # Stage unchanged; no update_stage event created.
        db.session.refresh(r)
        assert r.stage == "Weld Complete"


def test_welded_qc_with_tagged_photo_succeeds(app):
    with app.app_context():
        r = _make_release(1, "A")
        db.session.commit()
        _add_photo(r.id, "Welded QC")

        from app.brain.job_log.features.stage.command import UpdateStageCommand
        p = _patches()
        with p[0], p[1]:
            result = UpdateStageCommand(job_id=1, release="A", stage="Welded QC").execute()

        db.session.refresh(r)
        assert r.stage == "Welded QC"
        assert result.status == "success"


def test_photo_for_other_stage_does_not_satisfy(app):
    with app.app_context():
        r = _make_release(1, "A")
        db.session.commit()
        _add_photo(r.id, "Paint Complete")  # wrong stage tag

        from app.brain.job_log.features.stage.command import (
            UpdateStageCommand, StagePhotoRequiredError,
        )
        p = _patches()
        with p[0], p[1]:
            with pytest.raises(StagePhotoRequiredError):
                UpdateStageCommand(job_id=1, release="A", stage="Welded QC").execute()


def test_deleted_photo_does_not_satisfy(app):
    with app.app_context():
        r = _make_release(1, "A")
        db.session.commit()
        _add_photo(r.id, "Welded QC", is_deleted=True)

        from app.brain.job_log.features.stage.command import (
            UpdateStageCommand, StagePhotoRequiredError,
        )
        p = _patches()
        with p[0], p[1]:
            with pytest.raises(StagePhotoRequiredError):
                UpdateStageCommand(job_id=1, release="A", stage="Welded QC").execute()


def test_non_gated_stage_unaffected(app):
    with app.app_context():
        _make_release(1, "A", stage="Cut Start")
        db.session.commit()

        from app.brain.job_log.features.stage.command import UpdateStageCommand
        p = _patches()
        with p[0], p[1]:
            result = UpdateStageCommand(job_id=1, release="A", stage="Fitup Start").execute()
        assert result.status == "success"


def test_undo_bypasses_gate(app):
    # Re-entering a gated stage via undo (undone_event_id set) must not be blocked.
    with app.app_context():
        r = _make_release(1, "A")
        db.session.commit()

        from app.brain.job_log.features.stage.command import UpdateStageCommand
        p = _patches()
        with p[0], p[1]:
            result = UpdateStageCommand(
                job_id=1, release="A", stage="Welded QC", undone_event_id=999,
            ).execute()
        db.session.refresh(r)
        assert r.stage == "Welded QC"
        assert result.status == "success"


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------


def test_route_returns_422_photo_required(app):
    with app.app_context():
        _make_release(1, "A")
        db.session.commit()

        p = _patches()
        with p[0], p[1]:
            client = app.test_client()
            resp = client.patch("/brain/update-stage/1/A", json={"stage": "Welded QC"})

        assert resp.status_code == 422, resp.data
        body = resp.get_json()
        assert body["code"] == "photo_required"
        assert body["stage"] == "Welded QC"


def test_route_succeeds_with_photo(app):
    with app.app_context():
        r = _make_release(1, "A")
        db.session.commit()
        _add_photo(r.id, "Welded QC")

        p = _patches()
        with p[0], p[1]:
            client = app.test_client()
            resp = client.patch("/brain/update-stage/1/A", json={"stage": "Welded QC"})

        assert resp.status_code == 200, resp.data
        assert resp.get_json()["status"] == "success"
