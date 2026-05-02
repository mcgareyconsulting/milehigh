"""Tests for red-date (hard start_install) auto-clear cascade.

When a release reaches the "complete" zone — stage='Complete' (equivalently
job_comp='X') or invoiced='X' — any hard-date `start_install` should clear
automatically. This file covers all three trigger paths plus negative cases.
"""
from datetime import date

import pytest
from unittest.mock import patch

from app.models import Releases, ReleaseEvents, db


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        yield


def _make_release(job, release, **kwargs):
    defaults = dict(
        job=job,
        release=release,
        job_name="Test Job",
        stage="Cut start",
        stage_group="FABRICATION",
        fab_order=10,
    )
    defaults.update(kwargs)
    r = Releases(**defaults)
    db.session.add(r)
    db.session.flush()
    return r


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
