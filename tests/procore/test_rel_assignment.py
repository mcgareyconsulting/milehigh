"""
Unit tests for DRR "Rel" number assignment (app/procore/procore.py).

Rel numbers live in [100, 999]. They are assigned MANUALLY from the DWL submittal
popup (assign_rel_manual) -- creation no longer assigns one automatically. A Rel
is unique on the value alone (job-agnostic): it may not collide with an ACTIVE
job-log release (Releases, any job) nor with a pending (non-Closed) DRR submittal
already holding the number. next_rel_number suggests the next free value to
prefill the popup.
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
    assign_rel_manual,
    RelAssignmentError,
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


def _make_submittal(sid, type_, rel=None, rel_assigned_at=None, status=None, project_number="100"):
    return Submittals(
        submittal_id=str(sid),
        procore_project_id="1",
        project_number=project_number,
        type=type_,
        status=status,
        rel=rel,
        rel_assigned_at=rel_assigned_at,
    )


# --- next_rel_number suggestion ----------------------------------------------------

def test_first_rel_is_min(app):
    with app.app_context():
        assert next_rel_number() == REL_MIN


def test_next_rel_increments_from_most_recent(app):
    with app.app_context():
        now = datetime.utcnow()
        db.session.add(_make_submittal("a", DRR_TYPE, rel=100, status="Closed", rel_assigned_at=now - timedelta(minutes=2)))
        db.session.add(_make_submittal("b", DRR_TYPE, rel=101, status="Closed", rel_assigned_at=now - timedelta(minutes=1)))
        db.session.commit()
        # Most recently assigned is 101 -> next is 102 (by recency, not by max value).
        # Both are Closed so they don't themselves block.
        assert next_rel_number() == 102


def test_rel_wraps_after_max(app):
    with app.app_context():
        db.session.add(_make_submittal("a", DRR_TYPE, rel=REL_MAX, status="Closed", rel_assigned_at=datetime.utcnow()))
        db.session.commit()
        assert next_rel_number() == REL_MIN


def test_next_rel_skips_active_release_any_job(app):
    with app.app_context():
        db.session.add(_make_release(777, 100))  # active release 100 on some other job
        db.session.commit()
        # Job-agnostic: 100 is taken anywhere -> suggestion advances to 101.
        assert next_rel_number() == 101


def test_next_rel_skips_consecutive_taken_numbers(app):
    with app.app_context():
        for r in (100, 101, 102):
            db.session.add(_make_release(500 + r, r))  # different jobs, all active
        db.session.commit()
        assert next_rel_number() == 103


def test_next_rel_skips_pending_drr_submittal(app):
    with app.app_context():
        db.session.add(_make_submittal("p", DRR_TYPE, rel=100, status="Open", rel_assigned_at=datetime.utcnow()))
        db.session.commit()
        # A pending (non-Closed) DRR holds 100 -> suggestion skips to 101.
        assert next_rel_number() == 101


def test_next_rel_ignores_closed_drr_submittal(app):
    with app.app_context():
        now = datetime.utcnow()
        # Anchor (most recent) is 105 -> sequence starts at 106. A Closed DRR sits
        # exactly on 106; because Closed DRRs don't reserve their number, 106 is
        # handed out rather than skipped. (Were it Open, the suggestion would be 107.)
        db.session.add(_make_submittal("anchor", DRR_TYPE, rel=105, status="Closed", rel_assigned_at=now))
        db.session.add(_make_submittal("c", DRR_TYPE, rel=106, status="Closed", rel_assigned_at=now - timedelta(minutes=1)))
        db.session.commit()
        assert next_rel_number() == 106


@pytest.mark.parametrize("kwargs,reason", [
    ({"is_archived": True}, "archived release is reusable"),
    ({"is_active": False}, "inactive release is reusable"),
])
def test_inactive_release_does_not_block_rel(app, kwargs, reason):
    with app.app_context():
        db.session.add(_make_release(100, 100, **kwargs))
        db.session.commit()
        assert next_rel_number() == 100, reason


def test_non_numeric_release_value_is_ignored(app):
    with app.app_context():
        db.session.add(_make_release(100, "N/A"))
        db.session.commit()
        assert next_rel_number() == 100


def test_raises_when_every_number_taken(app):
    with app.app_context():
        with patch("app.procore.procore.REL_MIN", 100), \
             patch("app.procore.procore.REL_MAX", 102):
            for r in (100, 101, 102):
                db.session.add(_make_release(500 + r, r))
            db.session.commit()
            with pytest.raises(RuntimeError):
                next_rel_number()


# --- assign_rel_manual -------------------------------------------------------------

def test_assign_manual_happy_path(app):
    with app.app_context():
        drr = _make_submittal("y", DRR_TYPE, status="Open")
        db.session.add(drr)
        db.session.commit()
        assert assign_rel_manual(drr, 200) == 200
        assert drr.rel == 200
        assert drr.rel_assigned_at is not None


def test_assign_manual_accepts_string_input(app):
    with app.app_context():
        drr = _make_submittal("y2", DRR_TYPE, status="Open")
        db.session.add(drr)
        db.session.commit()
        assert assign_rel_manual(drr, " 305 ") == 305
        assert drr.rel == 305


def test_assign_manual_rejects_non_drr(app):
    with app.app_context():
        non_drr = _make_submittal("x", "Submittal for GC  Approval", status="Open")
        db.session.add(non_drr)
        db.session.commit()
        with pytest.raises(RelAssignmentError) as exc:
            assign_rel_manual(non_drr, 200)
        assert exc.value.code == "type"
        assert non_drr.rel is None


@pytest.mark.parametrize("bad", [99, 1000, "abc", None, 0, -5])
def test_assign_manual_rejects_out_of_range(app, bad):
    with app.app_context():
        drr = _make_submittal("r", DRR_TYPE, status="Open")
        db.session.add(drr)
        db.session.commit()
        with pytest.raises(RelAssignmentError) as exc:
            assign_rel_manual(drr, bad)
        assert exc.value.code == "range"
        assert drr.rel is None


def test_assign_manual_collision_with_active_release(app):
    with app.app_context():
        db.session.add(_make_release(777, 200))  # active release 200 on another job
        drr = _make_submittal("d", DRR_TYPE, status="Open")
        db.session.add(drr)
        db.session.commit()
        with pytest.raises(RelAssignmentError) as exc:
            assign_rel_manual(drr, 200)
        assert exc.value.code == "collision"
        assert drr.rel is None


@pytest.mark.parametrize("kwargs", [{"is_archived": True}, {"is_active": False}])
def test_assign_manual_inactive_release_does_not_block(app, kwargs):
    with app.app_context():
        db.session.add(_make_release(777, 200, **kwargs))
        drr = _make_submittal("d2", DRR_TYPE, status="Open")
        db.session.add(drr)
        db.session.commit()
        assert assign_rel_manual(drr, 200) == 200


def test_assign_manual_collision_with_pending_drr(app):
    with app.app_context():
        db.session.add(_make_submittal("other", DRR_TYPE, rel=200, status="Open", rel_assigned_at=datetime.utcnow()))
        drr = _make_submittal("d3", DRR_TYPE, status="Open")
        db.session.add(drr)
        db.session.commit()
        with pytest.raises(RelAssignmentError) as exc:
            assign_rel_manual(drr, 200)
        assert exc.value.code == "collision"


def test_assign_manual_closed_drr_does_not_block(app):
    with app.app_context():
        db.session.add(_make_submittal("closed", DRR_TYPE, rel=200, status="Closed", rel_assigned_at=datetime.utcnow()))
        drr = _make_submittal("d4", DRR_TYPE, status="Open")
        db.session.add(drr)
        db.session.commit()
        assert assign_rel_manual(drr, 200) == 200


def test_assign_manual_reassign_self_same_number(app):
    with app.app_context():
        drr = _make_submittal("d5", DRR_TYPE, rel=200, status="Open", rel_assigned_at=datetime.utcnow())
        db.session.add(drr)
        db.session.commit()
        # Re-assigning the same number to the same submittal is allowed (self excluded).
        assert assign_rel_manual(drr, 200) == 200


def test_assign_manual_reassign_self_new_number(app):
    with app.app_context():
        drr = _make_submittal("d6", DRR_TYPE, rel=200, status="Open", rel_assigned_at=datetime.utcnow())
        db.session.add(drr)
        db.session.commit()
        assert assign_rel_manual(drr, 201) == 201
        assert drr.rel == 201


# --- Integration: creation no longer assigns a Rel ---------------------------------
# These drive the real create_submittal_from_webhook (DB write included), mocking only
# the Procore HTTP fetches. They guard against an auto-assignment being reintroduced.

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


def test_create_webhook_does_not_assign_rel_for_drr(app):
    with app.app_context():
        created, record, err = _patched_create("9001", DRR_TYPE)
        assert created is True
        assert err is None
        assert record.rel is None
        assert record.rel_assigned_at is None


def test_create_webhook_does_not_assign_rel_for_non_drr(app):
    with app.app_context():
        created, record, err = _patched_create("9002", "Submittal for GC Approval")
        assert created is True
        assert record.rel is None
        assert record.rel_assigned_at is None
