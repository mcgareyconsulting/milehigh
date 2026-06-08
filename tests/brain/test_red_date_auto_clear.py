"""Tests for red-date (hard start_install) auto-clear cascade.

When a release reaches the "complete" zone — stage='Complete' (equivalently
job_comp='X') or invoiced='X' — any hard-date `start_install` should clear
automatically. This file covers all three trigger paths plus negative cases.
"""
from datetime import date

import pytest
from unittest.mock import patch

from app.models import Releases, ReleaseEvents, db
# Defaults (Cut Start / FABRICATION / fab_order 10 / "Test Job") match the root
# factory exactly, so this is a straight alias.
from tests.conftest import make_release as _make_release


@pytest.fixture(autouse=True)
def setup_auth(admin_session):
    yield


def _stage_command_patches():
    return [
        patch("app.services.outbox_service.OutboxService.add"),
        patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"),
        patch("app.brain.job_log.routes.get_list_id_by_stage", return_value="list-1"),
    ]


# ---------------------------------------------------------------------------
# UpdateStageCommand: stage -> Complete
# ---------------------------------------------------------------------------

class TestStageCompleteCascade:
    def test_stage_to_complete_clears_hard_date(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formula=None,
                start_install_formulaTF=False,  # hard date present
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(job_id=1, release="A", stage="Complete").execute()

            db.session.refresh(r)
            assert r.start_install_formulaTF is True
            assert r.start_install_formula is None
            assert result.extras.get("hard_date_cleared") is True

            # Child event linked to the parent update_stage event.
            stage_event = ReleaseEvents.query.filter_by(action="update_stage").first()
            children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_formulaTF"
            ]
            assert len(children) == 1
            assert children[0].payload.get("parent_event_id") == stage_event.id
            assert children[0].payload.get("reason") == "stage_set_to_complete"

    def test_stage_to_complete_no_hard_date_is_noop(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=None,
                start_install_formulaTF=True,  # formula-driven, no hard date
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(job_id=1, release="A", stage="Complete").execute()

            db.session.refresh(r)
            assert r.start_install_formulaTF is True  # unchanged
            assert "hard_date_cleared" not in result.extras

            children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_formulaTF"
            ]
            assert children == []

    def test_stage_to_install_complete_clears_hard_date_and_sets_job_comp(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formula=None,
                start_install_formulaTF=False,  # hard date present
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(
                    job_id=1, release="A", stage="Install Complete"
                ).execute()

            db.session.refresh(r)
            assert r.start_install_formulaTF is True
            assert r.job_comp == "X"  # Install Complete sets the Install Prog marker
            assert result.extras.get("hard_date_cleared") is True

            stage_event = ReleaseEvents.query.filter_by(action="update_stage").first()
            hard_date_children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_formulaTF"
            ]
            assert len(hard_date_children) == 1
            assert hard_date_children[0].payload.get("reason") == "stage_set_to_install_complete"
            assert hard_date_children[0].payload.get("parent_event_id") == stage_event.id

            job_comp_children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "job_comp"
            ]
            assert len(job_comp_children) == 1
            assert job_comp_children[0].payload.get("reason") == "stage_set_to_install_complete"

    def test_stage_to_complete_sets_job_comp(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Weld Start", job_comp=None)
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Complete").execute()

            db.session.refresh(r)
            assert r.stage == "Complete"
            assert r.job_comp == "X"  # Complete is part of the complete zone now

            job_comp_children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "job_comp"
            ]
            assert len(job_comp_children) == 1
            assert job_comp_children[0].payload.get("reason") == "stage_set_to_complete"

    def test_install_complete_to_complete_keeps_job_comp(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Install Complete",
                stage_group="COMPLETE",
                job_comp="X",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Complete").execute()

            db.session.refresh(r)
            assert r.stage == "Complete"
            assert r.job_comp == "X"  # moving within the complete zone keeps the 'X'

            # No job_comp event — neither a set nor a clear — for an in-zone move.
            job_comp_children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "job_comp"
            ]
            assert job_comp_children == []

    def test_stage_off_complete_clears_job_comp(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Complete",
                stage_group="COMPLETE",
                job_comp="X",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Weld Start").execute()

            db.session.refresh(r)
            assert r.stage == "Weld Start"
            assert r.job_comp is None  # leaving the complete zone clears the 'X'

            job_comp_children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "job_comp"
                and e.payload.get("reason") == "stage_changed_from_complete"
            ]
            assert len(job_comp_children) == 1

    def test_stage_off_install_complete_clears_job_comp(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Install Complete",
                stage_group="COMPLETE",
                job_comp="X",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Weld Start").execute()

            db.session.refresh(r)
            assert r.stage == "Weld Start"
            assert r.job_comp is None  # leaving Install Complete clears the 'X'

            job_comp_children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "job_comp"
                and e.payload.get("reason") == "stage_changed_from_install_complete"
            ]
            assert len(job_comp_children) == 1

    def test_stage_to_non_complete_does_not_clear(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Weld Start").execute()

            db.session.refresh(r)
            assert r.start_install_formulaTF is False  # hard date still intact


# ---------------------------------------------------------------------------
# update_job_comp route: job_comp -> 'X'
# ---------------------------------------------------------------------------

class TestJobCompCascade:
    def test_job_comp_x_clears_hard_date(self, app, admin_client):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-job-comp/1/A",
                json={"job_comp": "X"},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body.get("hard_date_cleared") is True

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install_formulaTF is True
            assert r2.job_comp == "X"
            assert r2.stage == "Install Complete"  # 'X' marks install complete

            children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_formulaTF"
                and e.payload.get("reason") == "job_comp_set_to_x"
            ]
            assert len(children) == 1

    def test_job_comp_already_x_is_noop(self, app, admin_client):
        with app.app_context():
            r = _make_release(
                1, "A",
                job_comp="X",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-job-comp/1/A",
                json={"job_comp": "X"},
            )
            assert resp.status_code == 200
            assert "hard_date_cleared" not in (resp.get_json() or {})

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            # We don't fire on no-transition, so the hard date sticks around
            # (consistent with: "only clear when the user marks it complete now").
            assert r2.start_install_formulaTF is False

    def test_job_comp_percent_does_not_clear(self, app, admin_client):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-job-comp/1/A",
                json={"job_comp": "0.5"},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install_formulaTF is False  # not cleared
            assert r2.stage == "Install Start"  # a percentage means install has begun
            assert r2.fab_order == 10  # fab_order untouched on percentage

    def test_job_comp_non_numeric_leaves_stage_unchanged(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", stage="Weld Start")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-job-comp/1/A",
                json={"job_comp": "MFP"},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.job_comp == "MFP"
            assert r2.stage == "Weld Start"  # non-numeric value is not install progress

    def test_job_comp_cleared_leaves_stage_unchanged(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", job_comp="X", stage="Install Complete")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-job-comp/1/A",
                json={"job_comp": ""},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert (r2.job_comp or "") == ""
            assert r2.stage == "Install Complete"  # clearing the cell does not touch the stage


# ---------------------------------------------------------------------------
# update_invoiced route: invoiced -> 'X'
# ---------------------------------------------------------------------------

class TestInvoicedCascade:
    def test_invoiced_x_clears_hard_date(self, app, admin_client):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-invoiced/1/A",
                json={"invoiced": "X"},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body.get("hard_date_cleared") is True

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install_formulaTF is True
            assert r2.invoiced == "X"

            children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_formulaTF"
                and e.payload.get("reason") == "invoiced_set_to_x"
            ]
            assert len(children) == 1

    def test_invoiced_non_x_does_not_clear(self, app, admin_client):
        with app.app_context():
            r = _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-invoiced/1/A",
                json={"invoiced": "MFP"},
            )
            assert resp.status_code == 200
            assert "hard_date_cleared" not in (resp.get_json() or {})

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install_formulaTF is False
            assert r2.invoiced == "MFP"

    def test_invoiced_already_x_is_noop(self, app, admin_client):
        with app.app_context():
            r = _make_release(
                1, "A",
                invoiced="X",
                start_install=date(2026, 6, 1),
                start_install_formulaTF=False,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-invoiced/1/A",
                json={"invoiced": "X"},
            )
            assert resp.status_code == 200
            assert "hard_date_cleared" not in (resp.get_json() or {})


# ---------------------------------------------------------------------------
# Helper: idempotency
# ---------------------------------------------------------------------------

class TestHelperIdempotency:
    def test_helper_noop_when_already_formula_driven(self, app):
        from app.brain.job_log.features.start_install.clear_hard_date_cascade import (
            clear_hard_date_cascade,
        )
        with app.app_context():
            r = _make_release(1, "A", start_install_formulaTF=True)
            db.session.commit()

            result = clear_hard_date_cascade(
                r, parent_event_id=999, reason="stage_set_to_complete"
            )
            assert result is False
            db.session.refresh(r)
            assert r.start_install_formulaTF is True
            # No child event written
            children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_formulaTF"
            ]
            assert children == []

    def test_helper_noop_when_formulaTF_is_none(self, app):
        from app.brain.job_log.features.start_install.clear_hard_date_cascade import (
            clear_hard_date_cascade,
        )
        with app.app_context():
            r = _make_release(1, "A", start_install_formulaTF=None)
            db.session.commit()

            result = clear_hard_date_cascade(
                r, parent_event_id=999, reason="stage_set_to_complete"
            )
            assert result is False
