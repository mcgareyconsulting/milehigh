"""
Tests for the rank-gated Trello ↔ Job Log stage sync (#70).

Two layers:
- TestRankGate: pure unit tests of TrelloListMapper.apply_trello_list_to_db
  using stub job objects. Verifies the rank gate skips echoes, blocks backward
  drags, blocks Hold inbound, allows forward catch-up, etc.
- TestUpdateStageCommandOutbound: integration tests of UpdateStageCommand
  with the in-memory SQLite app fixture. Verifies the outbound milestone gate
  has been replaced with target-list-differs, and that Hold transitions skip
  the outbox entirely.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.models import db
from app.api.helpers import STAGE_PROGRESSION_RANK
from app.trello.list_mapper import TrelloListMapper
from tests.conftest import make_release


# ---------------------------------------------------------------------------
# Fixtures (app, mock_admin_user are in tests/conftest.py)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _disable_stage_photo_gate():
    # Trello sync tests move releases across zones (incl. gated stages); the
    # photo gate is covered in tests/brain/test_stage_photo_gate.py.
    with patch("app.brain.job_log.features.stage.command.STAGE_PHOTO_GATES", set()):
        yield


@pytest.fixture(autouse=True)
def setup_auth(admin_session):
    yield


def stub_job(stage, job_id=1):
    """Lightweight stand-in for a Releases instance for pure rank-gate tests."""
    return SimpleNamespace(id=job_id, stage=stage, stage_group=None)


# ---------------------------------------------------------------------------
# Unit: TrelloListMapper.apply_trello_list_to_db rank gate
# ---------------------------------------------------------------------------

class TestRankGate:
    """The inbound rank gate — no DB required."""

    def test_echo_of_outbound_push_is_skipped(self):
        """DB at Welded QC (rank 9) + inbound 'Fit Up Complete.' (rank 4) → skip.

        This is the literal echo case: setting Welded QC in Brain pushes the
        card to 'Fit Up Complete.' (Welded QC's forward-mapped list); when the
        webhook bounces back, the gate skips it because DB is already ahead.
        """
        job = stub_job("Welded QC")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Fit Up Complete.", "op-1")
        assert applied is False
        assert job.stage == "Welded QC"

    def test_complete_to_shipping_completed_echo_is_skipped(self):
        """The literal #70 bug: DB Complete (high) + inbound 'Shipping completed'."""
        job = stub_job("Complete")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Shipping completed", "op-1")
        assert applied is False
        assert job.stage == "Complete"

    def test_exact_equal_rank_same_string_is_skipped(self):
        """DB Released (0) + inbound 'Released' (0) → skip (>= rule)."""
        job = stub_job("Released")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Released", "op-1")
        assert applied is False
        assert job.stage == "Released"

    def test_equal_rank_different_string_blocked(self):
        """Inbound at the same rank zone is blocked: the floor of the zone is
        the entry stage, so DB at the same rank is not 'behind'.

        DB 'Store at MHMW' (rank 12) + inbound Trello list
        'Store at MHMW for shipping' (floor rank 12) → skip.
        """
        job = stub_job("Store at MHMW")
        applied = TrelloListMapper.apply_trello_list_to_db(
            job, "Store at MHMW for shipping", "op-1"
        )
        assert applied is False
        assert job.stage == "Store at MHMW"

    def test_backward_drag_is_blocked(self):
        """Trello drag from a higher-rank list to a lower-rank list is silently ignored.

        Rollbacks must happen in Brain, not on Trello.
        """
        job = stub_job("Welded QC")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Released", "op-1")
        assert applied is False
        assert job.stage == "Welded QC"

    def test_forward_catch_up_applies(self):
        """DB behind Trello → DB catches up to the canonical floor stage of the
        inbound zone (not the raw list name)."""
        job = stub_job("Cut Complete")  # rank 3
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Fit Up Complete.", "op-1")
        assert applied is True
        assert job.stage == "Fitup Complete"

    def test_forward_catch_up_to_paint_complete(self):
        """DB Welded QC (9) + inbound 'Paint complete' (rank 11) → apply."""
        job = stub_job("Welded QC")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Paint complete", "op-1")
        assert applied is True
        assert job.stage == "Paint Complete"

    def test_hold_is_sticky_against_inbound(self):
        """DB Hold (rank 99) blocks every inbound, regardless of list."""
        for inbound in TrelloListMapper.VALID_TRELLO_LISTS:
            job = stub_job("Hold")
            applied = TrelloListMapper.apply_trello_list_to_db(job, inbound, "op-1")
            assert applied is False, f"Hold should block inbound '{inbound}'"
            assert job.stage == "Hold"

    def test_null_db_stage_seeds_from_inbound(self):
        """A release with no stage (rank -1) accepts an inbound to seed the DB."""
        job = stub_job(None)
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Released", "op-1")
        assert applied is True
        assert job.stage == "Released"

    def test_unknown_inbound_list_rejected(self):
        """Unknown Trello list name still produces no DB write."""
        job = stub_job("Welded QC")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Backlog", "op-1")
        assert applied is False
        assert job.stage == "Welded QC"

    def test_finer_grained_substage_protected(self):
        """Sub-stages within the 'Fit Up Complete.' Trello zone are protected.

        A bounce-back arriving as the list 'Fit Up Complete.' must not
        overwrite a finer-grained DB sub-stage. (Fitup Start is now in the
        'Released' zone; it's not in this set anymore.)
        """
        substages = ["Weld Start", "Weld Complete", "Welded QC", "Paint Start"]
        for stage in substages:
            job = stub_job(stage)
            applied = TrelloListMapper.apply_trello_list_to_db(
                job, "Fit Up Complete.", f"op-{stage}"
            )
            # All substages have rank >= the list's floor (Fitup Complete, rank 5),
            # so the gate skips and DB stays at the finer-grained stage.
            assert applied is False, f"Expected skip for sub-stage {stage}"
            assert job.stage == stage

    def test_stage_group_updated_on_apply(self):
        """When the gate applies, stage_group is also synced."""
        job = stub_job("Cut Complete")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Paint complete", "op-1")
        assert applied is True
        assert job.stage == "Paint Complete"
        # Paint Complete is in READY_TO_SHIP per STAGE_TO_GROUP
        assert job.stage_group == "READY_TO_SHIP"


class TestRankTableInvariants:
    """Sanity checks on the rank tables themselves (catch drift early)."""

    def test_every_forward_map_key_has_a_rank(self):
        """The import-time assertion enforces this; this test pins the contract."""
        forward_keys = set(TrelloListMapper.DB_STAGE_TO_TRELLO_LIST.keys())
        rank_keys = set(STAGE_PROGRESSION_RANK.keys())
        missing = forward_keys - rank_keys
        assert not missing, f"Missing rank entries: {missing}"

    def test_every_trello_list_has_a_rank(self):
        for list_name in TrelloListMapper.VALID_TRELLO_LISTS:
            assert list_name in TrelloListMapper.TRELLO_LIST_RANK, (
                f"Trello list {list_name!r} missing from TRELLO_LIST_RANK"
            )

    def test_hold_absent_from_forward_map(self):
        """Hold is intentionally not in the forward map — outbound sync skips
        the Trello move when stage=Hold rather than picking a list."""
        assert "Hold" not in TrelloListMapper.DB_STAGE_TO_TRELLO_LIST
        assert TrelloListMapper.get_trello_list_for_stage("Hold") is None

    def test_fit_up_complete_zone_floor_is_fitup_complete(self):
        """The floor of the 'Fit Up Complete.' Trello zone is rank 5
        (Fitup Complete) — Fitup Start now maps to the 'Released' zone."""
        assert TrelloListMapper.TRELLO_LIST_RANK["Fit Up Complete."] == 5

    def test_hold_rank_is_above_all_real_stages(self):
        max_real = max(
            r for s, r in STAGE_PROGRESSION_RANK.items() if s != "Hold"
        )
        assert STAGE_PROGRESSION_RANK["Hold"] > max_real, (
            "Hold sentinel must exceed every real stage rank to be sticky"
        )


# ---------------------------------------------------------------------------
# Integration: UpdateStageCommand outbound gate (Hold + target-differs)
# ---------------------------------------------------------------------------

class TestUpdateStageCommandOutbound:
    """The outbound milestone gate is now target-list-differs, plus Hold guard."""

    def _patches(self):
        """Common patches: OutboxService.add, scheduling cascade, list-id resolver."""
        return [
            patch("app.services.outbox_service.OutboxService.add"),
            patch(
                "app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"
            ),
            patch(
                "app.brain.job_log.routes.get_list_id_by_stage",
                return_value="fake-list-id-123",
            ),
        ]

    def test_set_to_complete_pushes_to_trello(self, app):
        """Setting DB to Complete pushes the card; with the milestone gate fixed,
        the forward-mapped list 'Ship Complete' differs from current list."""
        with app.app_context():
            make_release(
                1, "A", "Welded QC", "READY_TO_SHIP",
                trello_card_id="card-1", trello_list_name="Fit Up Complete.",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = self._patches()
            with patches[0] as m_add, patches[1], patches[2]:
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Complete")
                cmd.execute()

            assert m_add.called, "Expected outbox push for Complete transition"
            kwargs = m_add.call_args.kwargs
            assert kwargs.get("destination") == "trello"
            assert kwargs.get("action") == "move_card"

    def test_substage_within_same_zone_skips_outbox(self, app):
        """DB Welded QC (list 'Fitup Complete') → Paint Start (also forward-maps
        to 'Fitup Complete'). Target == current → no outbox push."""
        with app.app_context():
            make_release(
                1, "A", "Welded QC", "READY_TO_SHIP",
                trello_card_id="card-1", trello_list_name="Fit Up Complete.",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = self._patches()
            with patches[0] as m_add, patches[1], patches[2]:
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Paint Start")
                cmd.execute()

            assert not m_add.called, "Same-zone moves must not push to Trello"

    def test_cross_zone_move_pushes(self, app):
        """DB Welded QC (list 'Fitup Complete') → Paint complete (list 'Paint
        complete'). Target != current → push fires."""
        with app.app_context():
            make_release(
                1, "A", "Welded QC", "READY_TO_SHIP",
                trello_card_id="card-1", trello_list_name="Fit Up Complete.",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = self._patches()
            with patches[0] as m_add, patches[1], patches[2]:
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Paint Complete")
                cmd.execute()

            assert m_add.called, "Cross-zone moves must push to Trello"

    def test_hold_transition_skips_outbox(self, app):
        """Hold is a pause — the card stays where it is on Trello."""
        with app.app_context():
            make_release(
                1, "A", "Welded QC", "READY_TO_SHIP",
                trello_card_id="card-1", trello_list_name="Fit Up Complete.",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = self._patches()
            with patches[0] as m_add, patches[1], patches[2]:
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Hold")
                cmd.execute()

            assert not m_add.called, "Hold transition must not push to Trello"

    def test_no_trello_card_id_skips_outbox(self, app):
        """Releases without a Trello card never push regardless of stage."""
        with app.app_context():
            make_release(
                1, "A", "Welded QC", "READY_TO_SHIP",
                trello_card_id=None, trello_list_name=None,
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = self._patches()
            with patches[0] as m_add, patches[1], patches[2]:
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Complete")
                cmd.execute()

            assert not m_add.called, "Releases without a Trello card must not push"

    def test_store_at_shop_pushes_to_canonical_list(self, app):
        """DB 'Store at MHMW' forward-maps to 'Store at MHMW'.
        With card on a different list, push fires (proves the fixed gate
        catches non-VALID_TRELLO_LISTS DB stages too)."""
        with app.app_context():
            make_release(
                1, "A", "Welded QC", "READY_TO_SHIP",
                trello_card_id="card-1", trello_list_name="Fit Up Complete.",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = self._patches()
            with patches[0] as m_add, patches[1], patches[2]:
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Store at MHMW")
                cmd.execute()

            assert m_add.called, "DB stage 'Store at MHMW' must push to its canonical Trello list"
