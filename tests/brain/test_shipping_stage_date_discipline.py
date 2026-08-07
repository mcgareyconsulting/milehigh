"""N5 shipping-stage date discipline + Paint Complete hard-date intercept.

When a release enters Ship Planning or Ship Complete:
  - Formula/estimated dates → blank start_install + ship_date and lock (formulaTF=False)
    so scheduling does not re-estimate
  - Hard start_install → keep dates, wash color (start_install_no_color=True, ASAP off)

Paint Complete with a hard install date (or ASAP) auto-rolls to Ship Planning.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.models import Releases, ReleaseEvents, db
from tests.conftest import make_release as _make_release


@pytest.fixture(autouse=True)
def _disable_stage_photo_gate():
    with patch("app.brain.job_log.features.stage.command.STAGE_PHOTO_GATES", set()):
        yield


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
# Formula blanking at Ship Planning / Ship Complete
# ---------------------------------------------------------------------------

class TestFormulaDateBlanking:
    def test_ship_planning_blanks_formula_dates_and_locks(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Paint Complete",
                stage_group="READY_TO_SHIP",
                start_install=date(2026, 8, 15),
                ship_date=date(2026, 8, 14),
                comp_eta=date(2026, 8, 18),
                start_install_formula="=queue",
                start_install_formulaTF=True,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(
                    job_id=1, release="A", stage="Ship Planning"
                ).execute()

            db.session.refresh(r)
            assert r.stage == "Ship Planning"
            assert r.start_install is None
            assert r.ship_date is None
            assert r.comp_eta is None
            assert r.start_install_formula is None
            assert r.start_install_formulaTF is False
            assert result.extras.get("formula_dates_blanked") is True

            stage_event = ReleaseEvents.query.filter_by(action="update_stage").one()
            children = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "shipping_stage_formula_dates"
            ]
            assert len(children) == 1
            assert children[0].payload.get("parent_event_id") == stage_event.id
            assert children[0].payload.get("reason") == "stage_set_to_ship_planning"
            assert children[0].payload["old_value"]["start_install"] == "2026-08-15"
            assert children[0].payload["old_value"]["ship_date"] == "2026-08-14"

    def test_ship_complete_blanks_formula_dates(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Ship Planning",
                stage_group="READY_TO_SHIP",
                fab_order=2,
                start_install=date(2026, 9, 1),
                start_install_formulaTF=True,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(
                    job_id=1, release="A", stage="Ship Complete"
                ).execute()

            db.session.refresh(r)
            assert r.start_install is None
            assert r.start_install_formulaTF is False
            assert result.extras.get("formula_dates_blanked") is True

    def test_blanking_is_idempotent(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Ship Planning",
                stage_group="READY_TO_SHIP",
                fab_order=2,
                start_install=None,
                ship_date=None,
                start_install_formula=None,
                start_install_formulaTF=False,
                comp_eta=None,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(
                    job_id=1, release="A", stage="Ship Complete"
                ).execute()

            db.session.refresh(r)
            assert "formula_dates_blanked" not in result.extras
            blank_events = [
                e for e in ReleaseEvents.query.all()
                if isinstance(e.payload, dict)
                and e.payload.get("field") == "shipping_stage_formula_dates"
            ]
            assert blank_events == []


# ---------------------------------------------------------------------------
# Hard-date color wash
# ---------------------------------------------------------------------------

class TestHardDateWash:
    def test_ship_planning_washes_hard_date_keeps_value(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Paint Complete",
                stage_group="READY_TO_SHIP",
                start_install=date(2026, 8, 20),
                ship_date=date(2026, 8, 19),
                start_install_formula=None,
                start_install_formulaTF=False,
                start_install_asap=True,
                start_install_no_color=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(
                    job_id=1, release="A", stage="Ship Planning"
                ).execute()

            db.session.refresh(r)
            assert r.start_install == date(2026, 8, 20)
            assert r.ship_date == date(2026, 8, 19)
            assert r.start_install_formulaTF is False
            assert r.start_install_no_color is True
            assert r.start_install_asap is False
            assert result.extras.get("dates_washed") is True

            wash = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_no_color"
            ]
            assert len(wash) == 1
            assert wash[0].payload.get("reason") == "stage_set_to_ship_planning"

    def test_hard_install_no_ship_date_washes_and_keeps_install(self, app):
        """Hard install wins the fork; ship stays empty for the user to set later."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Store at MHMW",
                stage_group="READY_TO_SHIP",
                start_install=date(2026, 10, 1),
                ship_date=None,
                start_install_formulaTF=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Ship Planning").execute()

            db.session.refresh(r)
            assert r.start_install == date(2026, 10, 1)
            assert r.ship_date is None
            assert r.start_install_no_color is True


# ---------------------------------------------------------------------------
# Paint Complete intercept: hard date (non-ASAP)
# ---------------------------------------------------------------------------

class TestHardDatePaintCompleteIntercept:
    def test_paint_complete_with_hard_date_advances_to_ship_planning(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Paint Start",
                stage_group="READY_TO_SHIP",
                fab_order=12.5,
                start_install=date(2026, 8, 25),
                start_install_formulaTF=False,
                start_install_asap=False,
                trello_card_id="card-hd",
                trello_list_name="Paint start",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0] as outbox_add, patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Paint Complete").execute()

            db.session.refresh(r)
            assert r.stage == "Ship Planning"
            assert r.fab_order == 2
            # Hard date kept, color washed at Ship Planning.
            assert r.start_install == date(2026, 8, 25)
            assert r.start_install_no_color is True

            stage_event = ReleaseEvents.query.filter_by(action="update_stage").one()
            assert stage_event.payload["to"] == "Ship Planning"
            assert stage_event.payload.get("hard_date_intercepted") is True
            assert stage_event.payload.get("asap_intercepted") is None
            assert stage_event.payload.get("via") == "Paint Complete"
            assert outbox_add.call_count == 1

    def test_paint_complete_without_hard_date_or_asap_stays(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Paint Start",
                stage_group="READY_TO_SHIP",
                fab_order=12.5,
                start_install=date(2026, 8, 25),
                start_install_formulaTF=True,
                start_install_asap=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Paint Complete").execute()

            db.session.refresh(r)
            assert r.stage == "Paint Complete"
            # Not yet at a shipping stage — formula dates untouched.
            assert r.start_install == date(2026, 8, 25)
            assert r.start_install_formulaTF is True


# ---------------------------------------------------------------------------
# Setting a hard date while already at a shipping stage stays washed white
# ---------------------------------------------------------------------------

class TestHardDateSetAtShippingStage:
    def test_set_hard_date_at_ship_planning_stays_no_color(self, app):
        """After formula blank, user sets dates manually — N5 keeps them white, not green."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Ship Planning",
                stage_group="READY_TO_SHIP",
                fab_order=2,
                start_install=None,
                ship_date=None,
                start_install_formula=None,
                start_install_formulaTF=False,
                start_install_no_color=False,
            )
            db.session.commit()

            from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand
            with patch("app.brain.job_log.features.start_install.command.update_trello_card"), \
                 patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
                UpdateStartInstallCommand(
                    job_id=1,
                    release="A",
                    start_install=date(2026, 9, 10),
                ).execute()

            db.session.refresh(r)
            assert r.start_install == date(2026, 9, 10)
            assert r.start_install_formulaTF is False
            assert r.start_install_no_color is True
            assert r.start_install_asap is False

    def test_set_hard_date_before_shipping_is_colored(self, app):
        """Outside shipping stages, a hard date still gets normal green/yellow treatment."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Paint Start",
                stage_group="READY_TO_SHIP",
                start_install=None,
                start_install_formulaTF=True,
                start_install_no_color=False,
            )
            db.session.commit()

            from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand
            with patch("app.brain.job_log.features.start_install.command.update_trello_card"), \
                 patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
                UpdateStartInstallCommand(
                    job_id=1,
                    release="A",
                    start_install=date(2026, 9, 10),
                ).execute()

            db.session.refresh(r)
            assert r.start_install == date(2026, 9, 10)
            assert r.start_install_no_color is False
