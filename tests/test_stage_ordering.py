"""
Tests for unified fab_order ordering.

Covers:
- Pure utility functions (_normalize_stage, get_stage_position, clamp_fab_order, get_fixed_tier)
- get_fab_order_bounds DB queries (unified across all dynamic stages)
- Integration: UpdateFabOrderCommand clamping and collision cascade
- Integration: stage change route — fixed tiers and dynamic assignment
"""
import pytest
from unittest.mock import Mock, patch

from app import create_app
from app.models import Releases, db
from app.api.helpers import (
    _normalize_stage,
    _get_all_variants_for_stages,
    get_stage_position,
    get_fab_order_bounds,
    clamp_fab_order,
    get_fixed_tier,
    DYNAMIC_STAGE_ORDER,
    FIXED_TIER_STAGES,
)


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
    with patch('app.auth.utils.get_current_user', return_value=mock_admin_user):
        yield


@pytest.fixture
def client(app):
    return app.test_client()


def make_release(job, release, stage, stage_group, fab_order, job_name="Test"):
    r = Releases(
        job=job,
        release=release,
        job_name=job_name,
        stage=stage,
        stage_group=stage_group,
        fab_order=fab_order,
    )
    db.session.add(r)
    db.session.flush()
    return r


# ---------------------------------------------------------------------------
# Pure utility tests (no DB)
# ---------------------------------------------------------------------------

def test_normalize_stage_exact():
    assert _normalize_stage("Cut start") == "Cut start"


def test_normalize_stage_variant():
    result = _normalize_stage("CUT START")
    assert result is not None
    assert result.lower() == "cut start"


def test_normalize_stage_unknown():
    assert _normalize_stage("Flying Saucer") is None


def test_normalize_stage_none():
    assert _normalize_stage(None) is None


def test_get_stage_position_dynamic_stages():
    """Dynamic stages return their position in DYNAMIC_STAGE_ORDER."""
    assert get_stage_position("Welded QC") == 0
    assert get_stage_position("Welded") == 1
    assert get_stage_position("Fit Up Complete.") == 2
    assert get_stage_position("Material Ordered") == 3
    assert get_stage_position("Cut start") == 4
    assert get_stage_position("Released") == 5


def test_get_stage_position_fixed_tiers_return_none():
    """Fixed-tier stages are not in the dynamic order."""
    assert get_stage_position("Shipping Complete") is None
    assert get_stage_position("Shipping completed") is None
    assert get_stage_position("Complete") is None
    assert get_stage_position("Paint complete") is None
    assert get_stage_position("Store at MHMW for shipping") is None
    assert get_stage_position("Shipping planning") is None


def test_get_stage_position_hold_exempt():
    assert get_stage_position("Hold") is None


def test_get_stage_position_none():
    assert get_stage_position(None) is None


def test_get_fixed_tier():
    """Fixed-tier stages return their tier value."""
    assert get_fixed_tier("Shipping completed") == 1
    assert get_fixed_tier("Shipping Complete") == 1
    assert get_fixed_tier("Complete") == 1
    assert get_fixed_tier("Paint complete") == 2
    assert get_fixed_tier("Paint Complete") == 2
    assert get_fixed_tier("Store at MHMW for shipping") == 2
    assert get_fixed_tier("Shipping planning") == 2


def test_get_fixed_tier_dynamic_stages_return_none():
    """Dynamic stages are not fixed tiers."""
    assert get_fixed_tier("Released") is None
    assert get_fixed_tier("Cut start") is None
    assert get_fixed_tier("Welded") is None
    assert get_fixed_tier("Welded QC") is None
    assert get_fixed_tier("Hold") is None


def test_clamp_below_lower():
    assert clamp_fab_order(5, lower=10, upper=None) == 11


def test_clamp_above_upper():
    assert clamp_fab_order(20, lower=None, upper=15) == 14


def test_clamp_in_range():
    assert clamp_fab_order(12, lower=10, upper=15) == 12


def test_clamp_no_bounds():
    assert clamp_fab_order(7, lower=None, upper=None) == 7


def test_clamp_at_lower_boundary():
    assert clamp_fab_order(10, lower=10, upper=None) == 11


def test_clamp_at_upper_boundary():
    assert clamp_fab_order(15, lower=None, upper=15) == 15


def test_clamp_at_upper_boundary_strict():
    assert clamp_fab_order(15, lower=None, upper=15, strict_upper=True) == 14


def test_clamp_above_upper_strict():
    assert clamp_fab_order(20, lower=None, upper=15, strict_upper=True) == 14


# ---------------------------------------------------------------------------
# get_fab_order_bounds DB tests (unified across all dynamic stages)
# ---------------------------------------------------------------------------

def test_bounds_welded_qc_no_earlier_stages(app):
    """Welded QC (pos=0): no earlier dynamic stages; upper=min of Welded jobs."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        make_release(2, "A", "Welded", "FABRICATION", 15)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Welded QC", 99, "Z")
        assert lower is None
        assert upper == 10


def test_bounds_released_only_earlier_stages(app):
    """Released (pos=5, last): lower=max of all earlier stages; no later stages."""
    with app.app_context():
        make_release(1, "A", "Cut start", "FABRICATION", 20)
        make_release(2, "A", "Material Ordered", "FABRICATION", 15)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Released", 99, "Z")
        assert lower == 20  # max of all earlier stages
        assert upper is None


def test_bounds_welded_between_stages(app):
    """Welded (pos=1): lower=max(Welded QC), upper=min(Fit Up Complete onward)."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Fit Up Complete.", "FABRICATION", 20)
        make_release(3, "A", "Released", "FABRICATION", 30)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Welded", 99, "Z")
        assert lower == 5   # max of Welded QC
        assert upper == 20  # min of Fit Up Complete


def test_bounds_cross_group_unified(app):
    """Bounds work across old stage_groups — Welded QC and Welded are neighbors."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Fit Up Complete.", "FABRICATION", 15)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Welded", 99, "Z")
        assert lower == 5
        assert upper == 15


def test_bounds_hold_exempt(app):
    """Hold is exempt — always returns (None, None)."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 5)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Hold", 99, "Z")
        assert lower is None
        assert upper is None


def test_bounds_fixed_tier_exempt(app):
    """Fixed-tier stages return (None, None)."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 5)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Shipping completed", 99, "Z")
        assert lower is None
        assert upper is None

        lower, upper = get_fab_order_bounds("Paint complete", 99, "Z")
        assert lower is None
        assert upper is None


def test_bounds_self_excluded(app):
    """Current job is excluded from the query."""
    with app.app_context():
        make_release(10, "A", "Welded QC", "READY_TO_SHIP", 5)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Welded", 10, "A")
        assert lower is None
        assert upper is None


# ---------------------------------------------------------------------------
# Integration: UpdateFabOrderCommand
# ---------------------------------------------------------------------------

def test_fab_order_clamped_above_later_stage(app):
    """Welded QC tries fab_order=25 when Welded is at 10 → clamped to 9."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=25)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(wqc)
        assert wqc.fab_order == 9


def test_fab_order_clamped_below_earlier_stage(app):
    """Released tries fab_order=3 when Cut start is at 20 → clamped to 21."""
    with app.app_context():
        make_release(1, "A", "Cut start", "FABRICATION", 20)
        released = make_release(2, "A", "Released", "FABRICATION", 30)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=2, release="A", fab_order=3)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(released)
        assert released.fab_order == 21


def test_fab_order_min_is_3(app):
    """Dynamic fab_order is always at least 3 (1 and 2 are reserved)."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=1)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(wqc)
        assert wqc.fab_order >= 3


def test_fixed_tier_overrides_input(app):
    """Fixed-tier stage always gets the tier value regardless of input."""
    with app.app_context():
        complete = make_release(1, "A", "Complete", "COMPLETE", None)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=99)
        result = cmd.execute()

        db.session.refresh(complete)
        assert complete.fab_order == 1


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


def test_collision_cascade_unified(app):
    """Collision cascade works across all dynamic stages (not per stage_group)."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 3)
        welded = make_release(2, "A", "Welded", "FABRICATION", 5)
        fitup = make_release(3, "A", "Fit Up Complete.", "FABRICATION", 7)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        # Set Welded QC to 5 — should bump Welded and Fit Up
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(wqc)
        db.session.refresh(welded)
        db.session.refresh(fitup)
        assert wqc.fab_order == 5
        assert welded.fab_order == 6
        assert fitup.fab_order == 8


def test_collision_does_not_bump_fixed_tiers(app):
    """Fixed-tier releases (fab_order 1, 2) are never bumped by collision cascade."""
    with app.app_context():
        complete = make_release(1, "A", "Complete", "COMPLETE", 1)
        paint = make_release(2, "A", "Paint complete", "READY_TO_SHIP", 2)
        wqc = make_release(3, "A", "Welded QC", "READY_TO_SHIP", 4)
        welded = make_release(4, "A", "Welded", "FABRICATION", 5)
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
        assert welded.fab_order == 6


def test_full_chain_ordering_preserved(app):
    """After collision cascade, stage ordering is maintained across all dynamic stages."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 3)
        welded = make_release(2, "A", "Welded", "FABRICATION", 5)
        fitup = make_release(3, "A", "Fit Up Complete.", "FABRICATION", 8)
        released = make_release(4, "A", "Released", "FABRICATION", 12)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(wqc)
        db.session.refresh(welded)
        db.session.refresh(fitup)
        db.session.refresh(released)
        assert wqc.fab_order < welded.fab_order
        assert welded.fab_order < fitup.fab_order
        assert fitup.fab_order < released.fab_order


# ---------------------------------------------------------------------------
# Integration: stage change route
# ---------------------------------------------------------------------------

def test_stage_change_to_complete_sets_tier_1(client, app):
    """Moving to Complete auto-sets fab_order=1 and job_comp='X'."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Complete'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 1
        assert job.job_comp == 'X'


def test_stage_change_to_paint_complete_sets_tier_2(client, app):
    """Moving to Paint complete auto-sets fab_order=2."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Paint complete'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 2


def test_stage_change_to_dynamic_appends(client, app):
    """Moving to a dynamic stage appends at end of that stage's block."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 20)
        make_release(2, "A", "Welded", "FABRICATION", 5)
        make_release(3, "A", "Welded", "FABRICATION", 6)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Welded'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        # max in Welded = 6, so new fab_order = 7
        assert job.fab_order == 7


def test_stage_change_to_empty_dynamic_stage(client, app):
    """Moving to an empty dynamic stage gets lower_bound + 1 or 3."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 10)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Welded QC'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        # Welded QC is pos 0, no earlier stages → lower_bound = None → fab_order = 3
        assert job.fab_order == 3


def test_stage_change_to_welded_qc_with_earlier_empty(client, app):
    """Welded QC with no earlier stages starts at 3."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Welded QC'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 3


def test_stage_change_to_shipping_planning_sets_tier_2(client, app):
    """Shipping planning is a fixed tier 2 stage."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Shipping planning'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 2
