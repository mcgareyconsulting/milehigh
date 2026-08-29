"""BUG-11: a hard install date's color drops when install starts, not when it ships.

Bill reversed his own earlier rule — the color must survive the ship stages and drop
only once someone says work began, because a yellow overdue date is a scored EOS
metric that must never silently disappear.

Two things this pins that are easy to get wrong:
  * The trigger is the STAGE (`Install Start`), never the `start_install` DATE
    arriving. A date-driven dump fires on schedule straight through a slip, hiding
    exactly the overdue signal the rule exists to protect.
  * "Or later" is load-bearing — a release can jump Ship Planning -> `Complete` and
    skip `Install Start` entirely.

The ship stages leaving hard dates alone is covered in
tests/brain/test_shipping_stage_date_discipline.py.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.api.helpers import STAGE_HOUR_PERCENTAGES
from app.brain.job_log.features.start_install.neutralize_install_date_cascade import (
    COLOR_DUMP_STAGES,
    reason_for_stage,
)
from app.models import ReleaseEvents, db
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


def _hard_dated(stage="Ship Planning", **kw):
    r = _make_release(
        1, "A",
        stage=stage,
        start_install=date(2026, 9, 10),
        start_install_formulaTF=False,
        start_install_no_color=False,
        **kw,
    )
    db.session.commit()
    return r


def _move_to(stage):
    from app.brain.job_log.features.stage.command import UpdateStageCommand
    patches = _stage_command_patches()
    with patches[0], patches[1], patches[2]:
        return UpdateStageCommand(job_id=1, release="A", stage=stage).execute()


# --- the set itself --------------------------------------------------------

def test_color_dump_stages_are_install_start_and_everything_after_it():
    """Guards the hand-written tuple against the canonical stage order drifting.

    If a stage is ever inserted after `Install Start`, it belongs in the dump set;
    this is what makes 'or later' true rather than aspirational.
    """
    order = list(STAGE_HOUR_PERCENTAGES)
    expected = tuple(order[order.index("Install Start"):])
    assert COLOR_DUMP_STAGES == expected


def test_ship_stages_are_not_in_the_dump_set():
    assert "Ship Planning" not in COLOR_DUMP_STAGES
    assert "Ship Complete" not in COLOR_DUMP_STAGES


@pytest.mark.parametrize("stage,expected", [
    ("Install Start", "stage_set_to_install_start"),
    ("Install Complete", "stage_set_to_install_complete"),
    ("Complete", "stage_set_to_complete"),
])
def test_every_dump_stage_has_its_own_audit_reason(stage, expected):
    assert reason_for_stage(stage) == expected


# --- the dump --------------------------------------------------------------

@pytest.mark.parametrize("stage", ["Install Start", "Install Complete", "Complete"])
def test_entering_a_dump_stage_drops_the_color_and_keeps_the_date(app, stage):
    with app.app_context():
        r = _hard_dated()

        result = _move_to(stage)

        db.session.refresh(r)
        assert r.start_install == date(2026, 9, 10), "the date itself is never discarded"
        assert r.start_install_no_color is True
        assert result.extras.get("hard_date_cleared") is True


def test_install_start_records_its_own_reason(app):
    with app.app_context():
        _hard_dated()

        _move_to("Install Start")

        washes = [
            e for e in ReleaseEvents.query.all()
            if isinstance(e.payload, dict)
            and e.payload.get("field") == "start_install_no_color"
        ]
        assert len(washes) == 1
        assert washes[0].payload["reason"] == "stage_set_to_install_start"
        stage_event = ReleaseEvents.query.filter_by(action="update_stage").one()
        assert washes[0].payload["parent_event_id"] == stage_event.id


def test_skipping_install_start_still_dumps(app):
    """Ship Planning -> Complete, never touching `Install Start`. A bare equality
    check on `Install Start` would leave this release colored forever."""
    with app.app_context():
        r = _hard_dated(stage="Ship Planning")

        _move_to("Complete")

        db.session.refresh(r)
        assert r.start_install_no_color is True


def test_install_start_clears_asap_red(app):
    with app.app_context():
        r = _hard_dated(start_install_asap=True)

        _move_to("Install Start")

        db.session.refresh(r)
        assert r.start_install_asap is False
        assert r.start_install_no_color is True


def test_formula_dated_release_is_untouched_at_install_start(app):
    """Formula rows already render neutral; the dump has nothing to do and must not
    disturb the estimate or its recomputation."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Ship Complete",
            start_install=date(2026, 9, 10),
            start_install_formulaTF=True,
            start_install_no_color=False,
        )
        db.session.commit()

        result = _move_to("Install Start")

        db.session.refresh(r)
        assert r.start_install_formulaTF is True
        assert r.start_install_no_color is False
        assert result.extras.get("hard_date_cleared") is None


def test_dump_is_idempotent_across_the_zone(app):
    """Install Start -> Install Complete -> Complete washes once, not three times."""
    with app.app_context():
        _hard_dated()

        _move_to("Install Start")
        _move_to("Install Complete")
        _move_to("Complete")

        washes = [
            e for e in ReleaseEvents.query.all()
            if isinstance(e.payload, dict)
            and e.payload.get("field") == "start_install_no_color"
        ]
        assert len(washes) == 1


def test_date_arriving_does_not_dump_before_install_starts(app):
    """The trigger is the stage, never the date. A date set (even one in the past)
    at a pre-install stage stays colored, so an overdue install stays visible."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Ship Planning",
            start_install=None,
            start_install_formulaTF=False,
            start_install_no_color=False,
        )
        db.session.commit()

        from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand
        with patch("app.brain.job_log.features.start_install.command.update_trello_card"), \
             patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
            UpdateStartInstallCommand(
                job_id=1, release="A", start_install=date(2020, 1, 1),
            ).execute()

        db.session.refresh(r)
        assert r.start_install == date(2020, 1, 1)
        assert r.start_install_no_color is False


def test_date_set_by_hand_at_install_start_stays_neutral(app):
    """Once install has started the boundary applies to hand-set dates too, or a
    later edit would bring the color back one keystroke after the stage dropped it."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Install Start",
            start_install=None,
            start_install_formulaTF=False,
            start_install_no_color=False,
        )
        db.session.commit()

        from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand
        with patch("app.brain.job_log.features.start_install.command.update_trello_card"), \
             patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
            UpdateStartInstallCommand(
                job_id=1, release="A", start_install=date(2026, 9, 10),
            ).execute()

        db.session.refresh(r)
        assert r.start_install_no_color is True
