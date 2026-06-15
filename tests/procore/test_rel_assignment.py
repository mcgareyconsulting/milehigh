"""
Unit tests for DRR "Rel" number assignment (app/procore/procore.py).

Rel numbers live in [101, 998] (999 is a reserved special-job sentinel assigned
directly upstream, never via the popup). They are assigned MANUALLY from the DWL
submittal popup (assign_rel_manual) -- creation no longer assigns one
automatically. A Rel is unique on the value alone (job-agnostic): it may not
collide with an ACTIVE job-log release (Releases, any job) nor with a pending
(non-Closed) DRR submittal already holding the number. next_rel_number suggests
the next highest available value -- max-in-use + 1, climbing past gaps, rolling
over to the low 100s only once 998 is occupied -- to prefill the popup.
"""
from datetime import datetime
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
# Suggestion = max-in-use + 1 ("next highest available"), climbing past unused
# gaps, rolling over to the lowest free value only once REL_MAX (998) is occupied.

def test_first_rel_is_min(app):
    with app.app_context():
        assert next_rel_number() == REL_MIN


def test_next_rel_is_max_in_use_plus_one(app):
    with app.app_context():
        for r in (650, 651, 652):
            db.session.add(_make_release(500 + r, r))  # different jobs, all active
        db.session.commit()
        # Highest in use is 652 -> next is 653.
        assert next_rel_number() == 653


def test_next_rel_climbs_past_gap_not_back_to_low(app):
    with app.app_context():
        # 650-652 in use; 101-649 are free (e.g. never used or archived). The
        # suggestion must keep climbing (653), NOT drop back into the low gap.
        for r in (650, 651, 652):
            db.session.add(_make_release(500 + r, r))
        db.session.add(_make_release(101, 101, is_archived=True))  # freed low number
        db.session.commit()
        assert next_rel_number() == 653


def test_next_rel_ignores_gaps_below_the_max(app):
    with app.app_context():
        # A stray low active release does not pull the sequence down: max wins.
        db.session.add(_make_release(200, 200))
        db.session.add(_make_release(650, 650))
        db.session.commit()
        assert next_rel_number() == 651


def test_blocked_number_still_advances_to_next(app):
    with app.app_context():
        # 650, 651, 652 assigned; 653 is blocked (in use) -> next is 654, not low.
        for r in (650, 651, 652, 653):
            db.session.add(_make_release(500 + r, r))
        db.session.commit()
        assert next_rel_number() == 654


def test_rollover_to_low_once_max_occupied(app):
    with app.app_context():
        # Someone occupies REL_MAX (998) -> roll over to the lowest free value.
        db.session.add(_make_release(998, REL_MAX))
        db.session.commit()
        assert next_rel_number() == REL_MIN


def test_rollover_recycles_lowest_free(app):
    with app.app_context():
        # After rollover (998 occupied) the freed low numbers come back into play,
        # filling from the bottom up. 101 is free (archived) so it is reused.
        db.session.add(_make_release(998, REL_MAX))
        db.session.add(_make_release(102, 102))             # active, blocks 102
        db.session.add(_make_release(101, 101, is_archived=True))  # freed -> reusable
        db.session.commit()
        assert next_rel_number() == 101


def test_special_999_is_a_sentinel_not_in_sequence(app):
    with app.app_context():
        # 999 is reserved for special jobs (assigned directly). It is never
        # suggested and -- crucially -- does not count as "998 occupied", so it
        # must not trigger rollover. With only 999 in use, next is still REL_MIN.
        db.session.add(_make_release(999, 999))
        db.session.commit()
        assert next_rel_number() == REL_MIN


def test_special_999_does_not_become_the_max(app):
    with app.app_context():
        db.session.add(_make_release(999, 999))  # sentinel, out of range
        db.session.add(_make_release(650, 650))  # real high-water mark
        db.session.commit()
        assert next_rel_number() == 651


def test_next_rel_skips_pending_drr_submittal(app):
    with app.app_context():
        db.session.add(_make_submittal("p", DRR_TYPE, rel=300, status="Open", rel_assigned_at=datetime.utcnow()))
        db.session.commit()
        # A pending (non-Closed) DRR holds 300 -> it is the max in use -> next 301.
        assert next_rel_number() == 301


def test_next_rel_ignores_closed_drr_submittal(app):
    with app.app_context():
        now = datetime.utcnow()
        # Closed DRRs don't reserve their number, so 500 does not count toward the
        # max. Only the active release at 650 does -> next is 651.
        db.session.add(_make_submittal("closed", DRR_TYPE, rel=500, status="Closed", rel_assigned_at=now))
        db.session.add(_make_release(650, 650))
        db.session.commit()
        assert next_rel_number() == 651


@pytest.mark.parametrize("kwargs,reason", [
    ({"is_archived": True}, "archived release is reusable"),
    ({"is_active": False}, "inactive release is reusable"),
])
def test_inactive_release_does_not_block_rel(app, kwargs, reason):
    with app.app_context():
        db.session.add(_make_release(500, 500, **kwargs))
        db.session.commit()
        # Only an inactive release exists -> nothing in use -> first number.
        assert next_rel_number() == REL_MIN, reason


def test_non_numeric_release_value_is_ignored(app):
    with app.app_context():
        db.session.add(_make_release(500, "N/A"))
        db.session.commit()
        assert next_rel_number() == REL_MIN


def test_raises_when_every_number_taken(app):
    with app.app_context():
        with patch("app.procore.procore.REL_MIN", 101), \
             patch("app.procore.procore.REL_MAX", 103):
            for r in (101, 102, 103):
                db.session.add(_make_release(500 + r, r))
            db.session.commit()
            # 103 (REL_MAX) occupied -> rollover, but nothing free -> RuntimeError.
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


# 100 (below REL_MIN) and 999 (the reserved special-job sentinel) are out of the
# popup-assignable range and must be rejected.
@pytest.mark.parametrize("bad", [99, 100, 999, 1000, "abc", None, 0, -5])
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
