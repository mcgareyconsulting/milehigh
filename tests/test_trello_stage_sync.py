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

from app import create_app
from app.models import Releases, db
from app.api.helpers import STAGE_PROGRESSION_RANK
from app.trello.list_mapper import TrelloListMapper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"

    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    assert "sandbox" not in uri.lower() and "render.com" not in uri

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def mock_admin_user():
    user = Mock()
    user.id = 1
    user.username = "test_admin"
    user.is_admin = True
    user.is_active = True
    return user


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        yield


def make_release(
    job, release, stage, stage_group, fab_order=5,
    trello_card_id=None, trello_list_name=None, job_name="Test",
):
    r = Releases(
        job=job,
        release=release,
        job_name=job_name,
        stage=stage,
        stage_group=stage_group,
        fab_order=fab_order,
        trello_card_id=trello_card_id,
        trello_list_name=trello_list_name,
    )
    db.session.add(r)
    db.session.flush()
    return r


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
        """The literal #70 bug: DB Complete (15) + inbound 'Shipping completed' (14)."""
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
        """Variant rename via inbound is blocked: DB and Trello vocabularies stay separate.

        DB 'Store at Shop' (rank 12) + inbound 'Store at MHMW for shipping'
        (rank 12) → skip. DB keeps its job-log vocabulary.
        """
        job = stub_job("Store at Shop")
        applied = TrelloListMapper.apply_trello_list_to_db(
            job, "Store at MHMW for shipping", "op-1"
        )
        assert applied is False
        assert job.stage == "Store at Shop"

    def test_backward_drag_is_blocked(self):
        """Trello drag from a higher-rank list to a lower-rank list is silently ignored.

        Rollbacks must happen in Brain, not on Trello.
        """
        job = stub_job("Welded QC")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Released", "op-1")
        assert applied is False
        assert job.stage == "Welded QC"

    def test_forward_catch_up_applies(self):
        """DB behind Trello → DB catches up to the canonical Trello list name."""
        job = stub_job("Cut Complete")  # rank 3
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Fit Up Complete.", "op-1")
        assert applied is True
        assert job.stage == "Fit Up Complete."

    def test_forward_catch_up_to_paint_complete(self):
        """DB Welded QC (9) + inbound Paint complete (11) → apply."""
        job = stub_job("Welded QC")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Paint complete", "op-1")
        assert applied is True
        assert job.stage == "Paint complete"

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
        """All sub-stages mapping to 'Fit Up Complete.' are protected from clobber.

        A bounce-back arriving as the literal list name 'Fit Up Complete.' must
        not overwrite a finer-grained DB sub-stage.
        """
        substages = ["Fitup Start", "Weld Start", "Weld Complete", "Welded QC", "Paint Start"]
        for stage in substages:
            job = stub_job(stage)
            applied = TrelloListMapper.apply_trello_list_to_db(
                job, "Fit Up Complete.", f"op-{stage}"
            )
            # All substages have rank >= the list's floor (Fitup Start, rank 4),
            # so the gate skips and DB stays at the finer-grained stage.
            assert applied is False, f"Expected skip for sub-stage {stage}"
            assert job.stage == stage

    def test_stage_group_updated_on_apply(self):
        """When the gate applies, stage_group is also synced."""
        job = stub_job("Cut Complete")
        applied = TrelloListMapper.apply_trello_list_to_db(job, "Paint complete", "op-1")
        assert applied is True
        assert job.stage == "Paint complete"
        # Paint complete is in READY_TO_SHIP per STAGE_TO_GROUP
        assert job.stage_group == "READY_TO_SHIP"


class TestRankTableInvariants:
    """Sanity checks on the rank tables themselves (catch drift early)."""

    def test_every_forward_map_key_has_a_rank(self):
        """The import-time assertion enforces this; this test pins the contract."""
        forward_keys = set(TrelloListMapper.DB_STAGE_TO_TRELLO_LIST.keys()) - {"Hold"}
        rank_keys = set(STAGE_PROGRESSION_RANK.keys())
        missing = forward_keys - rank_keys
        assert not missing, f"Missing rank entries: {missing}"

    def test_every_trello_list_has_a_rank(self):
        for list_name in TrelloListMapper.VALID_TRELLO_LISTS:
            assert list_name in TrelloListMapper.TRELLO_LIST_RANK, (
                f"Trello list {list_name!r} missing from TRELLO_LIST_RANK"
            )

    def test_hold_excluded_from_trello_list_floor(self):
        """Hold's sentinel (99) must not raise the floor of 'Fit Up Complete.'."""
        # Fitup Start is rank 4 and forward-maps to "Fit Up Complete.", so the
        # floor of that list is 4 — not 99 (Hold).
        assert TrelloListMapper.TRELLO_LIST_RANK["Fit Up Complete."] == 4

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
        the forward-mapped list 'Shipping completed' differs from current list."""
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
        """DB Welded QC (list 'Fit Up Complete.') → Paint Start (also forward-maps
        to 'Fit Up Complete.'). Target == current → no outbox push."""
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
        """DB Welded QC (list 'Fit Up Complete.') → Paint complete (list 'Paint
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
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Paint complete")
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
        """DB 'Store at Shop' forward-maps to 'Store at MHMW for shipping'.
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
                cmd = UpdateStageCommand(job_id=1, release="A", stage="Store at Shop")
                cmd.execute()

            assert m_add.called, "DB stage 'Store at Shop' must push to its canonical Trello list"
