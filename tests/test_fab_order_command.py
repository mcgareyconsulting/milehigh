"""Integration tests for UpdateFabOrderCommand — clamping, no-cascade, bounded cascade."""
import pytest
from unittest.mock import patch

from app.models import Releases, db


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch('app.auth.utils.get_current_user', return_value=mock_admin_user):
        yield


def make_release(job, release, stage, stage_group, fab_order, job_name="Test"):
    r = Releases(
        job=job, release=release, job_name=job_name,
        stage=stage, stage_group=stage_group, fab_order=fab_order,
    )
    db.session.add(r)
    db.session.flush()
    return r


def test_fab_order_manual_edit_no_stage_bounds(app):
    """Manual edit is not clamped to stage bounds — fully manual ordering."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Weld Complete", "FABRICATION", 10)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=25)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(wqc)
        # No bounds clamping — value is accepted as-is
        assert wqc.fab_order == 25


def test_fab_order_manual_edit_accepts_any_value_above_3(app):
    """Manual edit accepts any value >= 3 regardless of other stages."""
    with app.app_context():
        make_release(1, "A", "Cut start", "FABRICATION", 20)
        released = make_release(2, "A", "Released", "FABRICATION", 30)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=2, release="A", fab_order=3)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(released)
        # No bounds clamping — value is accepted (>= 3 minimum)
        assert released.fab_order == 3


def test_fab_order_accepts_low_values_on_non_tier_stage(app):
    """Non-fixed-tier stages accept any user-provided fab_order — no floor."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=1)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(wqc)
        assert wqc.fab_order == 1


def test_complete_forces_null_fab_order(app):
    """Stage='Complete' is terminal — fab_order is always forced to NULL."""
    with app.app_context():
        complete = make_release(1, "A", "Complete", "COMPLETE", None)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=99)
        result = cmd.execute()

        db.session.refresh(complete)
        assert complete.fab_order is None


def test_shipping_completed_overrides_input(app):
    """Shipping completed (tier 1) always gets fab_order=1 regardless of input."""
    with app.app_context():
        sc = make_release(1, "A", "Shipping completed", "COMPLETE", None)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=99)
        result = cmd.execute()

        db.session.refresh(sc)
        assert sc.fab_order == 1


def test_fixed_tier_paint_complete(app):
    """Paint complete always gets fab_order=2."""
    with app.app_context():
        pc = make_release(1, "A", "Paint complete", "READY_TO_SHIP", None)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=50)
        result = cmd.execute()

        db.session.refresh(pc)
        assert pc.fab_order == 2


def test_hold_not_clamped(app):
    """Hold job ignores bounds entirely."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 5)
        hold_job = make_release(2, "A", "Hold", "FABRICATION", None)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=2, release="A", fab_order=3)
        result = cmd.execute()

        db.session.refresh(hold_job)
        assert hold_job.fab_order == 3


def test_no_cascade_allows_duplicates(app):
    """Setting fab_order to a value already used by another release does not shift others."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 3)
        welded = make_release(2, "A", "Weld Complete", "FABRICATION", 5)
        fitup = make_release(3, "A", "Fit Up Complete.", "FABRICATION", 7)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        # Set Welded QC from 3 to 5 — welded already at 5, should NOT be bumped
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(wqc)
        db.session.refresh(welded)
        db.session.refresh(fitup)
        assert wqc.fab_order == 5
        assert welded.fab_order == 5   # unchanged — duplicates allowed
        assert fitup.fab_order == 7    # unchanged


def test_fixed_tiers_unchanged_on_manual_edit(app):
    """Fixed-tier releases keep their values when other releases are edited."""
    with app.app_context():
        complete = make_release(1, "A", "Complete", "COMPLETE", 1)
        paint = make_release(2, "A", "Paint complete", "READY_TO_SHIP", 2)
        wqc = make_release(3, "A", "Welded QC", "READY_TO_SHIP", 4)
        welded = make_release(4, "A", "Weld Complete", "FABRICATION", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=3, release="A", fab_order=3)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(complete)
        db.session.refresh(paint)
        db.session.refresh(wqc)
        db.session.refresh(welded)
        assert complete.fab_order == 1  # unchanged
        assert paint.fab_order == 2     # unchanged
        assert wqc.fab_order == 3
        assert welded.fab_order == 5    # unchanged


def test_duplicate_fab_order_no_cascade(app):
    """Multiple releases can share the same fab_order without any shifting."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 3)
        welded = make_release(2, "A", "Weld Complete", "FABRICATION", 5)
        fitup = make_release(3, "A", "Fit Up Complete.", "FABRICATION", 8)
        released = make_release(4, "A", "Released", "FABRICATION", 12)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        # Move WQC from 3 to 5 — welded already at 5, no cascade
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(wqc)
        db.session.refresh(welded)
        db.session.refresh(fitup)
        db.session.refresh(released)
        assert wqc.fab_order == 5
        assert welded.fab_order == 5     # unchanged — duplicate allowed
        assert fitup.fab_order == 8      # unchanged
        assert released.fab_order == 12  # unchanged


# ---------------------------------------------------------------------------
# Bounded cascade tests
# ---------------------------------------------------------------------------
def test_no_cascade_move_earlier(app):
    """Moving earlier does not bump any other jobs — duplicates allowed."""
    with app.app_context():
        jobs = []
        for i, pos in enumerate([25, 26, 27, 28, 29, 30, 40, 41, 42]):
            jobs.append(make_release(i + 1, "A", "Weld Complete", "FABRICATION", pos))
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=7, release="A", fab_order=27)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        for j in jobs:
            db.session.refresh(j)

        assert jobs[0].fab_order == 25   # unchanged
        assert jobs[1].fab_order == 26   # unchanged
        assert jobs[2].fab_order == 27   # unchanged — duplicate with target
        assert jobs[3].fab_order == 28   # unchanged
        assert jobs[4].fab_order == 29   # unchanged
        assert jobs[5].fab_order == 30   # unchanged
        assert jobs[6].fab_order == 27   # target job
        assert jobs[7].fab_order == 41   # unchanged
        assert jobs[8].fab_order == 42   # unchanged


def test_no_cascade_move_later(app):
    """Moving later does not bump any other jobs — duplicates allowed."""
    with app.app_context():
        jobs = []
        for i, pos in enumerate([8, 9, 10, 11, 12, 13, 14, 15, 16]):
            jobs.append(make_release(i + 1, "A", "Weld Complete", "FABRICATION", pos))
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=3, release="A", fab_order=15)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        for j in jobs:
            db.session.refresh(j)

        assert jobs[0].fab_order == 8    # unchanged
        assert jobs[1].fab_order == 9    # unchanged
        assert jobs[2].fab_order == 15   # target job
        assert jobs[3].fab_order == 11   # unchanged
        assert jobs[4].fab_order == 12   # unchanged
        assert jobs[5].fab_order == 13   # unchanged
        assert jobs[6].fab_order == 14   # unchanged
        assert jobs[7].fab_order == 15   # unchanged — duplicate with target
        assert jobs[8].fab_order == 16   # unchanged


def test_no_cascade_move_by_one(app):
    """Moving by one position does not bump adjacent job."""
    with app.app_context():
        job_a = make_release(1, "A", "Weld Complete", "FABRICATION", 40)
        job_b = make_release(2, "A", "Weld Complete", "FABRICATION", 41)
        job_c = make_release(3, "A", "Weld Complete", "FABRICATION", 42)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=41)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(job_a)
        db.session.refresh(job_b)
        db.session.refresh(job_c)
        assert job_a.fab_order == 41
        assert job_b.fab_order == 41   # unchanged — duplicate
        assert job_c.fab_order == 42   # unchanged


def test_no_cascade_first_assignment(app):
    """First-time assignment (None → value) does not bump other jobs."""
    with app.app_context():
        target = make_release(1, "A", "Weld Complete", "FABRICATION", None)
        job_at_10 = make_release(2, "A", "Weld Complete", "FABRICATION", 10)
        job_at_11 = make_release(3, "A", "Weld Complete", "FABRICATION", 11)
        job_at_9 = make_release(4, "A", "Weld Complete", "FABRICATION", 9)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=10)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(target)
        db.session.refresh(job_at_10)
        db.session.refresh(job_at_11)
        db.session.refresh(job_at_9)
        assert target.fab_order == 10
        assert job_at_10.fab_order == 10  # unchanged — duplicate
        assert job_at_11.fab_order == 11  # unchanged
        assert job_at_9.fab_order == 9    # unchanged


def test_no_cascade_same_value_noop(app):
    """Setting fab_order to same value is a no-op."""
    with app.app_context():
        job_a = make_release(1, "A", "Weld Complete", "FABRICATION", 10)
        job_b = make_release(2, "A", "Weld Complete", "FABRICATION", 11)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=10)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(job_a)
        db.session.refresh(job_b)
        assert job_a.fab_order == 10  # unchanged
        assert job_b.fab_order == 11  # unchanged


# ---------------------------------------------------------------------------
# Archived release exemption
# ---------------------------------------------------------------------------
def test_no_cascade_archived_unaffected(app):
    """Setting fab_order does not affect any other jobs, including archived ones."""
    with app.app_context():
        target = make_release(1, "A", "Weld Complete", "FABRICATION", 15)
        active_job = make_release(2, "A", "Weld Complete", "FABRICATION", 10)
        archived_job = Releases(
            job=3, release="A", job_name="Archived", stage="Weld Complete",
            stage_group="FABRICATION", fab_order=10, is_archived=True,
        )
        db.session.add(archived_job)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=10)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(target)
        db.session.refresh(active_job)
        db.session.refresh(archived_job)
        assert target.fab_order == 10
        assert active_job.fab_order == 10   # unchanged — duplicate
        assert archived_job.fab_order == 10  # unchanged
