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

Every path that stamps a hard date decides its color the same way, off the one
`COLOR_DUMP_STAGES` boundary — the stage cascade, a hand-typed date, the ASAP
toggle and a Trello mirror-card edit. Each of the last three used to hardcode the
color on, which would light a dumped row back up.

The ship stages leaving hard dates alone is covered in
tests/brain/test_shipping_stage_date_discipline.py.
"""
from datetime import date
from unittest.mock import MagicMock, patch

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


# --- no date is ever rewritten, ASAP included ------------------------------

@pytest.mark.parametrize("stage", ["Install Start", "Install Complete", "Complete"])
def test_an_asap_rows_date_survives_the_dump_zone(app, stage):
    """An ASAP date used to be rewritten to the day install began — it was a placeholder
    anchor five business days out, never a plan. ASAP stamps no date now: an ASAP row's
    date is one a person typed, so it is a commitment like any other and must not move."""
    with app.app_context():
        r = _hard_dated(start_install_asap=True)
        assert r.start_install == date(2026, 9, 10)

        _move_to(stage)

        db.session.refresh(r)
        assert r.start_install == date(2026, 9, 10)
        assert r.start_install_no_color is True
        assert r.start_install_asap is False, "the red comes off with the rest of the colour"
        assert not any(
            isinstance(e.payload, dict) and e.payload.get("field") == "start_install"
            for e in ReleaseEvents.query.all()
        ), "nothing rewrote the date, so nothing is audited as having done so"


def test_a_hand_set_hard_date_is_never_rewritten(app):
    """A date someone chose is a real commitment — colour drops, date stays.
    This is the 'date not changed, just colour' half of the rule."""
    with app.app_context():
        r = _hard_dated(start_install_asap=False)

        _move_to("Install Start")

        db.session.refresh(r)
        assert r.start_install == date(2026, 9, 10)
        assert r.start_install_no_color is True
        assert not any(
            isinstance(e.payload, dict) and e.payload.get("field") == "start_install"
            for e in ReleaseEvents.query.all()
        )


def test_job_comp_cascade_does_not_rewrite_an_asap_date(app):
    """The job_comp and invoiced cascades share the neutralize helper. Like every other
    caller they take the colour and leave the date."""
    with app.app_context():
        r = _hard_dated(stage="Install Start", start_install_asap=True)
        from app.brain.job_log.features.start_install.neutralize_install_date_cascade import (
            neutralize_install_date_cascade,
        )
        from app.services.job_event_service import JobEventService

        parent = JobEventService.create_and_close(
            job=1, release="A", action="updated", source="Brain",
            payload={"field": "job_comp", "old_value": None, "new_value": "X"},
        )
        neutralize_install_date_cascade(
            r, parent_event_id=parent.id, reason="job_comp_set_to_x",
        )
        db.session.commit()

        db.session.refresh(r)
        assert r.start_install == date(2026, 9, 10)
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


# --- other paths that stamp a hard date -----------------------------------

def test_asap_can_be_flagged_before_install_starts(app, client):
    """The normal case: ASAP paints the row red and leaves the date to the user."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Ship Planning",
            start_install=None,
            start_install_formulaTF=True,
            start_install_asap=False,
            start_install_no_color=False,
            install_hrs=8,
            num_guys=2,
        )
        db.session.commit()

        with patch("app.brain.job_log.routes.update_trello_card"), \
             patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
            resp = client.patch(
                "/brain/update-start-install/1/A",
                json={"asap": True},
            )

        assert resp.status_code == 200, resp.get_data(as_text=True)
        db.session.refresh(r)
        assert r.start_install_asap is True
        assert r.start_install is None, "the flag sets no date; the user still has to"
        assert r.start_install_no_color is False


@pytest.mark.parametrize("stage", ["Install Start", "Install Complete", "Complete"])
def test_asap_is_refused_once_install_has_started(app, client, stage):
    """ASAP is a rush flag on work that has not started. Past `Install Start` it is
    meaningless, and honoring it would repaint a row whose color was already dumped."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage=stage,
            start_install=date(2026, 9, 10),
            start_install_formulaTF=False,
            start_install_asap=False,
            start_install_no_color=True,
            install_hrs=8,
            num_guys=2,
        )
        db.session.commit()

        with patch("app.brain.job_log.routes.update_trello_card"), \
             patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
            resp = client.patch(
                "/brain/update-start-install/1/A",
                json={"asap": True},
            )

        assert resp.status_code == 409
        assert resp.get_json()["error"] == "asap_after_install_start"

        db.session.refresh(r)
        assert r.start_install_asap is False, "the flag must not be set"
        assert r.start_install == date(2026, 9, 10), "the refusal must not touch the date"
        assert r.start_install_no_color is True


def test_clearing_asap_is_still_allowed_after_install_starts(app, client):
    """Only setting is refused — a stale flag must always be clearable."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Install Start",
            start_install=date(2026, 9, 10),
            start_install_formulaTF=False,
            start_install_asap=True,
        )
        db.session.commit()

        with patch("app.brain.job_log.routes.update_trello_card"), \
             patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
            resp = client.patch(
                "/brain/update-start-install/1/A",
                json={"asap": False},
            )

        assert resp.status_code == 200, resp.get_data(as_text=True)
        db.session.refresh(r)
        assert r.start_install_asap is False


def test_asap_undo_leaves_the_users_date_alone(app, client):
    """set_asap writes the flag and the colour bit, so its undo puts back exactly those
    two. The hard date belongs to the user's own save and must survive the undo."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Ship Planning",
            start_install=date(2026, 9, 10),
            start_install_formulaTF=False,
            start_install_no_color=False,
            install_hrs=8,
            num_guys=2,
        )
        db.session.commit()

        with patch("app.brain.job_log.routes.update_trello_card"), \
             patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
            client.patch("/brain/update-start-install/1/A", json={"asap": True})
            db.session.refresh(r)
            assert r.start_install_asap is True

            set_event = ReleaseEvents.query.filter_by(action="set_asap").one()
            resp = client.post(f"/brain/events/{set_event.id}/undo")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        db.session.refresh(r)
        assert r.start_install_asap is False
        assert r.start_install == date(2026, 9, 10), "the user's date is not the flag's to undo"
        assert r.start_install_formulaTF is False
        assert r.start_install_no_color is False


def test_undoing_a_legacy_asap_still_restores_its_stamped_date(app, client):
    """Events recorded before ASAP stopped stamping a date carry prev_start_install.
    Undoing one has to put the whole date-state back, or the +1wk placeholder it wrote
    would be left behind on the row."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Ship Planning",
            start_install=date(2026, 9, 10),
            start_install_formulaTF=False,
            start_install_asap=True,
            start_install_no_color=False,
        )
        from app.services.job_event_service import JobEventService
        legacy = JobEventService.create_and_close(
            job=1, release="A", action="set_asap", source="Brain",
            payload={
                "from": False, "to": True,
                "prev_start_install": None,
                "prev_comp_eta": None,
                "prev_formulaTF": True,
                "prev_no_color": False,
                "new_start_install": "2026-09-10",
            },
        )
        db.session.commit()

        with patch("app.trello.api.update_trello_card"), \
             patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
            resp = client.post(f"/brain/events/{legacy.id}/undo")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        db.session.refresh(r)
        assert r.start_install_asap is False
        assert r.start_install is None, "the placeholder it stamped is rolled back"
        assert r.start_install_formulaTF is True


@pytest.mark.parametrize("stage,expected_no_color", [
    ("Ship Planning", False),
    ("Install Start", True),
])
def test_trello_mirror_date_slide_colors_by_stage(app, stage, expected_no_color):
    """The installer team slides the mirror card's start bar. The new date is written
    back verbatim either way; only its color follows the stage, so a slide can't
    resurrect color on a release whose color was already dumped."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage=stage,
            start_install=date(2026, 9, 1),
            start_install_formulaTF=False,
            start_install_no_color=expected_no_color,
            mirror_trello_card_id="mirror-1",
            trello_card_id=None,
        )
        db.session.commit()

        from app.trello.sync import _handle_mirror_writeback
        handled = _handle_mirror_writeback(
            "mirror-1",
            {"start": "2026-09-15T12:00:00.000Z", "due": None},
            {"change_types": ["start_date_change"], "trello_user_id": None,
             "time": "2026-09-15T12:00:00.000Z"},
            MagicMock(operation_id="op-1"),
        )

        assert handled is True
        db.session.refresh(r)
        assert r.start_install == date(2026, 9, 15), "the slid date is written back verbatim"
        assert r.start_install_no_color is expected_no_color


# --- Install Prog: the third writer that advances a stage ------------------
#
# The Install Prog column moves the stage itself instead of going through
# UpdateStageCommand: a percentage means install BEGAN (-> `Install Start`), an 'X'
# means it FINISHED (-> `Install Complete`). The 'X' branch always ran the colour
# cascade; the percentage branch ran nothing, so the most explicit "work began"
# signal in the system was the one path that kept the row red (prod row 190-917).

def _install_prog(client, value):
    with patch("app.brain.job_log.routes.update_trello_card"), \
         patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
        return client.patch("/brain/update-job-comp/1/A", json={"job_comp": value})


def test_install_prog_percentage_moves_to_install_start_and_dumps_colour(app, client):
    with app.app_context():
        r = _hard_dated(stage="Ship Complete", start_install_asap=True)

        resp = _install_prog(client, "90")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        db.session.refresh(r)
        assert r.job_comp == "90%"
        assert r.stage == "Install Start"
        assert r.start_install_asap is False, "reporting progress means it is no longer a rush"
        assert r.start_install_no_color is True, "BUG-11: colour drops once install begins"
        assert r.start_install == date(2026, 9, 10), "the date itself never moves"


def test_install_prog_percentage_links_its_cascades_to_the_job_comp_event(app, client):
    """Both children hang off the job_comp event so the undo endpoint can bundle them."""
    with app.app_context():
        _hard_dated(stage="Ship Complete", start_install_asap=True)

        _install_prog(client, "90")

        primary = [
            e for e in ReleaseEvents.query.all()
            if isinstance(e.payload, dict) and e.payload.get("field") == "job_comp"
        ]
        assert len(primary) == 1
        children = [
            e for e in ReleaseEvents.query.all()
            if isinstance(e.payload, dict)
            and e.payload.get("parent_event_id") == primary[0].id
        ]
        reasons = {e.payload.get("reason") for e in children}
        assert "asap_dropped_on_ship_complete" in reasons
        assert reason_for_stage("Install Start") in reasons


def test_install_prog_percentage_drops_asap_on_a_formula_dated_row(app, client):
    """The colour cascade no-ops without a hard date. The ASAP drop is flag-only and
    must fire anyway, or a formula-dated rush row would keep its red forever."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Ship Complete",
            start_install=None,
            start_install_formulaTF=True,
            start_install_asap=True,
        )
        db.session.commit()

        _install_prog(client, "50")

        db.session.refresh(r)
        assert r.stage == "Install Start"
        assert r.start_install_asap is False


def test_install_prog_x_drops_asap_on_a_formula_dated_row(app, client):
    """Same gap on the 'X' branch: its neutralize cascade clears the flag only on a
    hard-dated row, so the flag-only drop has to run there too."""
    with app.app_context():
        r = _make_release(
            1, "A",
            stage="Ship Complete",
            start_install=None,
            start_install_formulaTF=True,
            start_install_asap=True,
        )
        db.session.commit()

        _install_prog(client, "X")

        db.session.refresh(r)
        assert r.stage == "Install Complete"
        assert r.start_install_asap is False


def test_install_prog_x_still_dumps_colour_and_keeps_the_date(app, client):
    """The branch that already worked keeps working."""
    with app.app_context():
        r = _hard_dated(stage="Ship Complete", start_install_asap=True)

        _install_prog(client, "X")

        db.session.refresh(r)
        assert r.stage == "Install Complete"
        assert r.start_install_asap is False
        assert r.start_install_no_color is True
        assert r.start_install == date(2026, 9, 10)


def test_install_prog_non_numeric_moves_nothing(app, client):
    """'MFP' is neither a percentage nor an X — it is a note, and notes move no stage."""
    with app.app_context():
        r = _hard_dated(stage="Ship Planning", start_install_asap=True)

        _install_prog(client, "MFP")

        db.session.refresh(r)
        assert r.job_comp == "MFP"
        assert r.stage == "Ship Planning"
        assert r.start_install_asap is True
        assert r.start_install_no_color is False
