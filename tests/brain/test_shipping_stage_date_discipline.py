"""N5 late-stage date discipline + Paint Complete hard-date intercept.

Two rules, two triggers (BUG-11 split them apart on 2026-08-21):
  - Ship Planning / Ship Complete → formula/estimated dates blank and lock
    (formulaTF=False) so scheduling does not re-estimate. A HARD date is left
    entirely alone here, colour included.
  - Install Start (the stage — not a start_install date being set) → a hard date
    keeps its value and loses its colour (start_install_no_color=True, ASAP off).

Yellow overdue has to survive the ship stages: it is a scored EOS metric, and
hiding it early is "sweeping an issue under the rug".

Paint Complete with a hard install date (or ASAP) auto-rolls to Ship Planning.
"""
from datetime import date, timedelta
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
    def test_ship_planning_leaves_hard_date_colored(self, app):
        """BUG-11: the ship stages no longer touch a hard date — colour and all."""
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
            assert r.start_install_no_color is False
            assert r.start_install_asap is True
            assert result.extras.get("dates_washed") is None

            wash = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_no_color"
            ]
            assert wash == []

    def test_ship_complete_leaves_hard_date_colored(self, app):
        """The whole ship leg carries the colour through, not just Ship Planning."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Ship Planning",
                stage_group="READY_TO_SHIP",
                start_install=date(2026, 10, 1),
                ship_date=date(2026, 9, 30),
                start_install_formulaTF=False,
                start_install_no_color=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Ship Complete").execute()

            db.session.refresh(r)
            assert r.start_install == date(2026, 10, 1)
            assert r.ship_date == date(2026, 9, 30)
            assert r.start_install_no_color is False

    def test_overdue_yellow_survives_the_ship_stages(self, app):
        """The one Bill called out: an overdue date must not vanish before install.

        A yellow overdue date is a scored EOS metric, so it has to stay readable all
        the way to Install Start rather than being swept away at the truck.
        """
        with app.app_context():
            overdue = date.today() - timedelta(days=10)
            r = _make_release(
                1, "A",
                stage="Store at MHMW",
                stage_group="READY_TO_SHIP",
                start_install=overdue,
                start_install_formulaTF=False,
                start_install_no_color=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            for next_stage in ("Ship Planning", "Ship Complete"):
                patches = _stage_command_patches()
                with patches[0], patches[1], patches[2]:
                    UpdateStageCommand(job_id=1, release="A", stage=next_stage).execute()
                db.session.refresh(r)
                assert r.start_install == overdue, next_stage
                assert r.start_install_no_color is False, next_stage

            # ...and only lets go once install actually starts.
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Install Start").execute()
            db.session.refresh(r)
            assert r.start_install == overdue
            assert r.start_install_no_color is True


# ---------------------------------------------------------------------------
# BUG-11: the colour dump fires on the Install Start STAGE
# ---------------------------------------------------------------------------

class TestInstallStartColorDump:
    def test_install_start_washes_hard_date_keeps_value(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Ship Complete",
                stage_group="COMPLETE",
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
                    job_id=1, release="A", stage="Install Start"
                ).execute()

            db.session.refresh(r)
            # Date kept — only the colour goes.
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
            assert wash[0].payload.get("reason") == "stage_set_to_install_start"

    def test_install_start_without_hard_date_is_a_no_op(self, app):
        """A formula-dated release at Install Start keeps its estimate untouched."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Ship Complete",
                stage_group="COMPLETE",
                start_install=date(2026, 8, 20),
                start_install_formulaTF=True,
                start_install_no_color=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(
                    job_id=1, release="A", stage="Install Start"
                ).execute()

            db.session.refresh(r)
            assert r.start_install == date(2026, 8, 20)
            assert r.start_install_formulaTF is True
            assert r.start_install_no_color is False
            assert result.extras.get("dates_washed") is None

    def test_install_start_wash_is_idempotent(self, app):
        """Re-entering Install Start emits no second wash event."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Install Start",
                stage_group="COMPLETE",
                start_install=date(2026, 8, 20),
                start_install_formulaTF=False,
                start_install_no_color=True,
                start_install_asap=False,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                result = UpdateStageCommand(
                    job_id=1, release="A", stage="Install Start"
                ).execute()

            db.session.refresh(r)
            assert r.start_install_no_color is True
            assert result.extras.get("dates_washed") is None
            wash = [
                e for e in ReleaseEvents.query.all()
                if e.action == "updated"
                and isinstance(e.payload, dict)
                and e.payload.get("field") == "start_install_no_color"
            ]
            assert wash == []


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
            # Hard date kept AND still coloured — the intercept moves the stage, it
            # does not dump colour (BUG-11).
            assert r.start_install == date(2026, 8, 25)
            assert r.start_install_no_color is False

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
    def test_set_hard_date_at_ship_planning_is_colored(self, app):
        """After a formula blank the user re-enters a date — it is a live commitment.

        Under the 2026-08-15 rule this stayed white. BUG-11 reversed that: nothing is
        colourless until the release reaches Install Start.
        """
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
            assert r.start_install_no_color is False
            assert r.start_install_asap is False

    def test_set_hard_date_at_install_start_is_colorless(self, app):
        """Past the colour dump, a newly entered date comes in neutral."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Install Start",
                stage_group="COMPLETE",
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
            assert r.start_install_no_color is True

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
