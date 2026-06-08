"""
Unit tests for DRR "Rel" number assignment (app/procore/procore.py).

Rel numbers are assigned per DRR submittal, sequentially in [100, 999], wrapping
back to 100 after 999. They are only assigned to submittals whose type is
"Drafting Release Review" (DRR) and that do not already have a Rel. A collision
guard skips any candidate already held by an ACTIVE job-log release (Releases) on
the same job so the job-release pair stays unique.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import db, Submittals, Releases
from app.procore.procore import (
    DRR_TYPE,
    REL_MIN,
    REL_MAX,
    next_rel_number,
    assign_rel_if_drr,
    create_submittal_from_webhook,
)


def _make_release(job, release, *, is_active=True, is_archived=False):
    """Minimal job-log Releases row for collision-guard tests."""
    return Releases(
        job=int(job),
        release=str(release),
        job_name="Test Job",
        is_active=is_active,
        is_archived=is_archived,
    )


def _make_submittal(sid, type_, rel=None, rel_assigned_at=None):
    return Submittals(
        submittal_id=str(sid),
        procore_project_id="1",
        project_number="100",
        type=type_,
        rel=rel,
        rel_assigned_at=rel_assigned_at,
    )


def test_first_rel_is_min(app):
    with app.app_context():
        assert next_rel_number() == REL_MIN


def test_next_rel_increments_from_most_recent(app):
    with app.app_context():
        now = datetime.utcnow()
        db.session.add(_make_submittal("a", DRR_TYPE, rel=100, rel_assigned_at=now - timedelta(minutes=2)))
        db.session.add(_make_submittal("b", DRR_TYPE, rel=101, rel_assigned_at=now - timedelta(minutes=1)))
        db.session.commit()
        # Most recently assigned is 101 -> next is 102 (not max+1 by value, by recency)
        assert next_rel_number() == 102


def test_rel_wraps_after_max(app):
    with app.app_context():
        db.session.add(_make_submittal("a", DRR_TYPE, rel=REL_MAX, rel_assigned_at=datetime.utcnow()))
        db.session.commit()
        assert next_rel_number() == REL_MIN


def test_assign_only_for_drr(app):
    with app.app_context():
        non_drr = _make_submittal("x", "Submittal for GC  Approval")
        db.session.add(non_drr)
        db.session.commit()
        assert assign_rel_if_drr(non_drr) is None
        assert non_drr.rel is None


def test_assign_sets_rel_and_timestamp(app):
    with app.app_context():
        drr = _make_submittal("y", DRR_TYPE)
        db.session.add(drr)
        db.session.commit()
        assigned = assign_rel_if_drr(drr)
        assert assigned == REL_MIN
        assert drr.rel == REL_MIN
        assert drr.rel_assigned_at is not None


def test_assign_is_idempotent(app):
    with app.app_context():
        drr = _make_submittal("z", DRR_TYPE, rel=250, rel_assigned_at=datetime.utcnow())
        db.session.add(drr)
        db.session.commit()
        # Already has a Rel -> no change, returns None
        assert assign_rel_if_drr(drr) is None
        assert drr.rel == 250


def test_sequential_assignment_across_multiple_drr(app):
    with app.app_context():
        assigned = []
        for i in range(3):
            s = _make_submittal(f"s{i}", DRR_TYPE)
            db.session.add(s)
            assign_rel_if_drr(s)
            db.session.commit()
            assigned.append(s.rel)
        assert assigned == [100, 101, 102]


# --- Integration: the create webhook path actually performs the assignment ---------
# These drive the real create_submittal_from_webhook (DB write included), mocking only
# the Procore HTTP fetches. They guard against the assignment call being removed or
# re-disabled, which the helper-only tests above would not catch.

def _patched_create(submittal_id, type_name):
    """Run create_submittal_from_webhook with Procore fetches stubbed for ``type_name``."""
    submittal_data = {
        "type": {"name": type_name},
        "status": {"name": "Open"},
        "title": "Some Submittal",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with patch("app.procore.procore.get_submittal_by_id", return_value=submittal_data), \
         patch("app.procore.procore.get_project_info",
               return_value={"name": "Proj", "project_number": "100"}), \
         patch("app.procore.procore.parse_ball_in_court_from_submittal",
               return_value={"ball_in_court": None}), \
         patch("app.procore.procore.parse_and_log_submittal_data", return_value=None):
        return create_submittal_from_webhook(1, submittal_id)


def test_create_webhook_assigns_rel_for_drr(app):
    with app.app_context():
        created, record, err = _patched_create("9001", DRR_TYPE)
        assert created is True
        assert err is None
        assert record.rel == REL_MIN
        assert record.rel_assigned_at is not None


def test_create_webhook_skips_rel_for_non_drr(app):
    with app.app_context():
        created, record, err = _patched_create("9002", "Submittal for GC Approval")
        assert created is True
        assert record.rel is None
        assert record.rel_assigned_at is None


# --- Job-release collision guard ---------------------------------------------------
# A Rel must not collide with an ACTIVE job-log release (Releases.job, Releases.release)
# on the same job. Archived/inactive releases, and releases on other jobs, don't block.
# Submittals.project_number is the same job number as Releases.job.

def test_rel_skips_number_held_by_active_release_on_same_job(app):
    with app.app_context():
        db.session.add(_make_release(100, 100))  # job 100 already holds active release 100
        db.session.commit()
        # Global sequence would start at REL_MIN (100); 100 is taken on job 100 -> 101.
        assert next_rel_number("100") == 101


def test_rel_skips_consecutive_taken_numbers(app):
    with app.app_context():
        for r in (100, 101, 102):
            db.session.add(_make_release(100, r))
        db.session.commit()
        assert next_rel_number("100") == 103


@pytest.mark.parametrize("release_job,kwargs,reason", [
    (100, {"is_archived": True}, "archived release is reusable"),
    (100, {"is_active": False}, "inactive release is reusable"),
    (999, {}, "active release on a different job doesn't block"),
])
def test_release_does_not_block_rel(app, release_job, kwargs, reason):
    # In each case job 100's release 100 is free, so the global sequence's first
    # candidate (REL_MIN) is handed out unchanged.
    with app.app_context():
        db.session.add(_make_release(release_job, 100, **kwargs))
        db.session.commit()
        assert next_rel_number("100") == 100, reason


def test_non_numeric_release_value_is_ignored(app):
    with app.app_context():
        db.session.add(_make_release(100, "N/A"))
        db.session.commit()
        assert next_rel_number("100") == 100


def test_raises_when_every_number_taken_for_job(app):
    with app.app_context():
        with patch("app.procore.procore.REL_MIN", 100), \
             patch("app.procore.procore.REL_MAX", 102):
            for r in (100, 101, 102):
                db.session.add(_make_release(100, r))
            db.session.commit()
            with pytest.raises(RuntimeError):
                next_rel_number("100")


def test_create_webhook_advances_past_active_job_release(app):
    with app.app_context():
        # Job 100 already has active job-log release 100; the global sequence would
        # otherwise hand 100 to the new DRR. The guard must advance to 101, and the
        # resulting job-release pair must not collide with an active release.
        db.session.add(_make_release(100, 100))
        db.session.commit()
        created, record, err = _patched_create("9100", DRR_TYPE)
        assert created is True
        assert record.rel == 101
        clash = Releases.query.filter_by(
            job=100, release="101", is_archived=False
        ).first()
        assert clash is None
