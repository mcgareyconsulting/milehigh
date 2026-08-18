"""BUG-9: one fab_order tier rule set, applied by every path that writes a stage.

Bill's report was two symptoms of one cause: "when we're getting to the paint
department and then complete, it's not flipping the two and the one… the fab
order is being cleared and not cleared." The tier rules only ever ran inside
UpdateStageCommand, so the Trello inbound sync (how the shop actually moves
work) never re-tiered at all, and the job_comp route answered the same question
differently.

These tests pin the rules themselves, then each write path against them.
"""
from unittest.mock import patch

import pytest

from app.api.helpers import DEFAULT_FAB_ORDER
from app.brain.job_log.features.fab_order.tier import (
    RESERVED_TIER_CEILING,
    plan_fab_order_for_stage,
)
from app.models import ReleaseEvents, Releases, db
from tests.conftest import make_release as _make_release


@pytest.fixture(autouse=True)
def setup_auth(admin_session):
    yield


def _stage_command_patches():
    return (
        patch("app.services.outbox_service.OutboxService.add"),
        patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"),
        patch("app.brain.job_log.routes.get_list_id_by_stage", return_value="list-1"),
    )


def _run_stage(job, release, stage):
    from app.brain.job_log.features.stage.command import UpdateStageCommand

    a, b, c = _stage_command_patches()
    with a, b, c:
        return UpdateStageCommand(job_id=job, release=release, stage=stage).execute()


# ---------------------------------------------------------------------------
# The rules, independent of who applies them
# ---------------------------------------------------------------------------

class TestPlan:
    @pytest.mark.parametrize("stage,expected", [
        ("Install Start", 0),
        ("Install Complete", 0),
        ("Ship Complete", 1),
        ("Paint Complete", 2),
        ("Store at MHMW", 2),
        ("Ship Planning", 2),
    ])
    def test_fixed_tier_stages_take_their_tier(self, app, stage, expected):
        with app.app_context():
            r = _make_release(1, "A", stage="Weld Complete", fab_order=42)
            plan = plan_fab_order_for_stage(r, stage)
            assert plan is not None and plan.fab_order == expected

    def test_paint_complete_to_ship_complete_flips_two_to_one(self, app):
        """The literal report: 2 → 1 at the paint → ship handoff."""
        with app.app_context():
            r = _make_release(1, "A", stage="Paint Complete", stage_group="READY_TO_SHIP", fab_order=2)
            plan = plan_fab_order_for_stage(r, "Ship Complete", "READY_TO_SHIP")
            assert plan is not None and plan.fab_order == 1

    def test_complete_is_terminal(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Complete", fab_order=1)
            plan = plan_fab_order_for_stage(r, "Complete")
            assert plan is not None and plan.fab_order is None

    def test_already_correct_is_a_no_op(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Complete", fab_order=1)
            assert plan_fab_order_for_stage(r, "Ship Complete") is None

    def test_hold_keeps_its_position(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Weld Start", fab_order=7)
            assert plan_fab_order_for_stage(r, "Hold") is None

    def test_valid_dynamic_position_is_left_to_the_user(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Cut Start", fab_order=12)
            assert plan_fab_order_for_stage(r, "Cut Complete") is None

    def test_dynamic_stage_never_keeps_a_reserved_tier_value(self, app):
        """Coming back down from shipping used to leave a 1 on a fab row, which
        sorts it in front of the entire shop."""
        with app.app_context():
            _make_release(2, "B", stage="Weld Complete", fab_order=11)
            r = _make_release(1, "A", stage="Ship Complete", fab_order=1)
            db.session.flush()

            plan = plan_fab_order_for_stage(r, "Weld Complete", "COMPLETE")
            assert plan is not None
            assert plan.fab_order >= RESERVED_TIER_CEILING
            assert plan.fab_order == 12  # back of the Weld Complete deck

    def test_reopened_from_complete_gets_a_position_back(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Complete", stage_group="COMPLETE", fab_order=None)
            plan = plan_fab_order_for_stage(r, "Weld Start", "COMPLETE")
            assert plan is not None and plan.fab_order >= RESERVED_TIER_CEILING

    def test_released_repairs_to_the_placeholder(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Complete", fab_order=1)
            plan = plan_fab_order_for_stage(r, "Released", "COMPLETE")
            assert plan is not None and plan.fab_order == DEFAULT_FAB_ORDER

    def test_paint_handoff_lands_at_the_back_of_the_booth(self, app):
        with app.app_context():
            _make_release(2, "B", stage="Paint Start", stage_group="READY_TO_SHIP", fab_order=9)
            r = _make_release(1, "A", stage="Weld Complete", fab_order=20)
            db.session.flush()

            plan = plan_fab_order_for_stage(r, "Welded QC", "FABRICATION")
            assert plan is not None and plan.fab_order == 10

    def test_placeholder_rows_do_not_define_the_back_of_the_deck(self, app):
        with app.app_context():
            _make_release(2, "B", stage="Paint Start", stage_group="READY_TO_SHIP",
                          fab_order=DEFAULT_FAB_ORDER)
            r = _make_release(1, "A", stage="Weld Complete", fab_order=20)
            db.session.flush()

            plan = plan_fab_order_for_stage(r, "Welded QC", "FABRICATION")
            assert plan is not None and plan.fab_order == 3

    def test_unknown_stage_is_left_alone(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Cut Start", fab_order=5)
            assert plan_fab_order_for_stage(r, "Wat") is None


# ---------------------------------------------------------------------------
# Every write path agrees
# ---------------------------------------------------------------------------

class TestWritePathsAgree:
    def test_stage_command_applies_the_tier(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Paint Complete", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()

            result = _run_stage(1, "A", "Ship Complete")

            db.session.refresh(r)
            assert r.fab_order == 1
            assert result.extras.get("fab_order") == 1

            child = ReleaseEvents.query.filter_by(action="update_fab_order").first()
            assert child is not None
            assert child.payload["from"] == 2 and child.payload["to"] == 1
            assert child.payload["parent_event_id"] is not None

    def test_stage_command_clears_at_complete(self, app):
        with app.app_context():
            r = _make_release(1, "A", stage="Ship Complete", stage_group="COMPLETE", fab_order=1)
            db.session.commit()

            _run_stage(1, "A", "Complete")

            db.session.refresh(r)
            assert r.fab_order is None

    def test_job_comp_x_and_stage_command_reach_the_same_state(self, app, admin_client):
        """The 'cleared and not cleared' half: the same end stage, reached two
        ways, used to leave fab_order NULL one way and tier 0 the other."""
        with app.app_context():
            via_route = _make_release(1, "A", stage="Paint Complete",
                                      stage_group="READY_TO_SHIP", fab_order=2)
            via_command = _make_release(2, "B", stage="Paint Complete",
                                        stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()

            resp = admin_client.patch("/brain/update-job-comp/1/A", json={"job_comp": "X"})
            assert resp.status_code == 200
            _run_stage(2, "B", "Install Complete")

            db.session.expire_all()
            a = Releases.query.filter_by(job=1, release="A").first()
            b = Releases.query.filter_by(job=2, release="B").first()
            assert a.stage == b.stage == "Install Complete"
            assert a.fab_order == b.fab_order == 0

    def test_trello_list_move_re_tiers(self, app):
        """The shop's actual path. A card dragged out of the paint list used to
        advance the stage and leave fab_order sitting on 2."""
        with app.app_context():
            from app.trello.list_mapper import TrelloListMapper
            from app.brain.job_log.features.fab_order.tier import apply_fab_order_for_stage

            r = _make_release(1, "A", stage="Paint Complete", stage_group="READY_TO_SHIP",
                              fab_order=2, trello_card_id="card-1")
            db.session.commit()

            old_stage_group = r.stage_group
            applied = TrelloListMapper.apply_trello_list_to_db(r, "Shipping completed", "op-1")
            assert applied is True

            plan = apply_fab_order_for_stage(
                r, r.stage, old_stage_group, source="Trello", stage_reason="trello_list_move",
            )
            db.session.commit()

            assert plan is not None
            assert r.fab_order == 1  # tier for the Ship Complete zone
            child = ReleaseEvents.query.filter_by(action="update_fab_order").first()
            assert child is not None and child.payload["to"] == 1

    def test_field_is_written_even_when_the_event_deduplicates(self, app):
        """A dropped audit event must never leave fab_order stale — the old
        inline code wrote the field only inside `if event:`."""
        with app.app_context():
            from app.brain.job_log.features.fab_order import tier

            r = _make_release(1, "A", stage="Paint Complete", stage_group="READY_TO_SHIP", fab_order=2)
            db.session.commit()

            with patch.object(tier.JobEventService, "create", return_value=None):
                plan = tier.apply_fab_order_for_stage(r, "Ship Complete", "READY_TO_SHIP")

            assert plan is not None and plan.fab_order == 1
            assert r.fab_order == 1
