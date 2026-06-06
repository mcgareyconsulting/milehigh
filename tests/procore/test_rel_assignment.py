"""
Unit tests for DRR "Rel" number assignment (app/procore/procore.py).

Rel numbers are assigned per DRR submittal, sequentially in [100, 999], wrapping
back to 100 after 999. They are only assigned to submittals whose type is
"Drafting Release Review" (DRR) and that do not already have a Rel.
"""
from datetime import datetime, timedelta

import pytest

from app.models import db, Submittals
from app.procore.procore import (
    DRR_TYPE,
    REL_MIN,
    REL_MAX,
    next_rel_number,
    assign_rel_if_drr,
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
