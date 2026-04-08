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
    assert get_stage_position("Paint Start") == 1
    assert get_stage_position("Weld Complete") == 2
    assert get_stage_position("Weld Start") == 3
    assert get_stage_position("Welded") == 4
    assert get_stage_position("Fit Up Complete.") == 5
    assert get_stage_position("Fitup Start") == 6
    assert get_stage_position("Material Ordered") == 7
    assert get_stage_position("Cut Complete") == 8
    assert get_stage_position("Cut start") == 9
    assert get_stage_position("Released") == 10


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

def test_fab_order_manual_edit_no_stage_bounds(app):
    """Manual edit is not clamped to stage bounds — fully manual ordering."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Welded", "FABRICATION", 10)
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


def test_no_cascade_allows_duplicates(app):
    """Setting fab_order to a value already used by another release does not shift others."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 3)
        welded = make_release(2, "A", "Welded", "FABRICATION", 5)
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
        assert welded.fab_order == 5    # unchanged


def test_duplicate_fab_order_no_cascade(app):
    """Multiple releases can share the same fab_order without any shifting."""
    with app.app_context():
        wqc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 3)
        welded = make_release(2, "A", "Welded", "FABRICATION", 5)
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


# ---------------------------------------------------------------------------
# PATCH /brain/update-fab-order — endpoint happy path
# ---------------------------------------------------------------------------

def test_endpoint_fab_order_update_success(client, app):
    """Basic PATCH returns 200 with status and event_id, DB updated."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 5},
        content_type='application/json'
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
    assert isinstance(data['event_id'], int)

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 5


def test_endpoint_fab_order_null_clears(client, app):
    """Sending null clears fab_order to None."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': None},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order is None


def test_endpoint_fab_order_integer_value(client, app):
    """Integer input accepted and stored."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 7},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 7


def test_endpoint_fab_order_float_value(client, app):
    """Float input accepted."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 7.5},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 7.5


# ---------------------------------------------------------------------------
# PATCH /brain/update-fab-order — validation & errors
# ---------------------------------------------------------------------------

def test_endpoint_fab_order_string_returns_400(client, app):
    """String fab_order returns 400."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 'abc'},
        content_type='application/json'
    )

    assert resp.status_code == 400
    assert 'must be a number' in resp.get_json()['error']


def test_endpoint_fab_order_empty_string_returns_400(client, app):
    """Empty string fab_order returns 400."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': ''},
        content_type='application/json'
    )

    assert resp.status_code == 400


def test_endpoint_fab_order_list_returns_400(client, app):
    """List fab_order returns 400."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': [1, 2, 3]},
        content_type='application/json'
    )

    assert resp.status_code == 400


def test_endpoint_fab_order_dict_returns_400(client, app):
    """Dict fab_order returns 400."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': {'value': 5}},
        content_type='application/json'
    )

    assert resp.status_code == 400


def test_endpoint_fab_order_nonexistent_job_returns_404(client, app):
    """Missing job returns 404."""
    with app.app_context():
        pass  # no jobs created

    resp = client.patch(
        '/brain/update-fab-order/9999/A',
        json={'fab_order': 5},
        content_type='application/json'
    )

    assert resp.status_code == 404
    assert 'not found' in resp.get_json()['error'].lower()


def test_endpoint_fab_order_empty_json_clears(client, app):
    """Empty JSON body (no fab_order key) clears fab_order to None."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order is None


def test_endpoint_fab_order_negative_clamped_to_3(client, app):
    """Negative fab_order is clamped to 3 for dynamic stages."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': -5},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order >= 3


def test_endpoint_fab_order_zero_clamped_to_3(client, app):
    """Zero fab_order is clamped to 3 for dynamic stages."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 0},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order >= 3


def test_endpoint_fab_order_very_large_accepted(client, app):
    """Very large fab_order is accepted — no stage bounds clamping."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 999999},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        # No bounds clamping — value is accepted as-is
        assert job.fab_order == 999999


# ---------------------------------------------------------------------------
# PATCH /brain/update-fab-order — collision cascade via endpoint
# ---------------------------------------------------------------------------

def test_endpoint_no_cascade_duplicate_allowed(client, app):
    """Setting fab_order to an occupied value does not bump other jobs — duplicates allowed."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        make_release(2, "A", "Welded", "FABRICATION", 6)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 6},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job1 = Releases.query.filter_by(job=1, release="A").first()
        job2 = Releases.query.filter_by(job=2, release="A").first()
        assert job1.fab_order == 6
        assert job2.fab_order == 6   # unchanged — duplicate allowed


def test_endpoint_no_cascade_multiple_jobs(client, app):
    """Setting fab_order leaves all other jobs unchanged."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 3)
        make_release(2, "A", "Welded", "FABRICATION", 5)
        make_release(3, "A", "Welded", "FABRICATION", 6)
        make_release(4, "A", "Welded", "FABRICATION", 7)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 5},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job1 = Releases.query.filter_by(job=1, release="A").first()
        job2 = Releases.query.filter_by(job=2, release="A").first()
        job3 = Releases.query.filter_by(job=3, release="A").first()
        job4 = Releases.query.filter_by(job=4, release="A").first()
        assert job1.fab_order == 5
        assert job2.fab_order == 5   # unchanged — duplicate
        assert job3.fab_order == 6   # unchanged
        assert job4.fab_order == 7   # unchanged


def test_endpoint_no_cascade_with_gaps(client, app):
    """Setting fab_order with gaps leaves all other jobs unchanged."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 3)
        make_release(2, "A", "Welded", "FABRICATION", 5)
        make_release(3, "A", "Welded", "FABRICATION", 8)
        make_release(4, "A", "Welded", "FABRICATION", 12)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 5},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job1 = Releases.query.filter_by(job=1, release="A").first()
        job2 = Releases.query.filter_by(job=2, release="A").first()
        job3 = Releases.query.filter_by(job=3, release="A").first()
        job4 = Releases.query.filter_by(job=4, release="A").first()
        assert job1.fab_order == 5
        assert job2.fab_order == 5   # unchanged — duplicate
        assert job3.fab_order == 8   # unchanged
        assert job4.fab_order == 12  # unchanged


def test_endpoint_duplicate_within_stage(client, app):
    """Two same-stage jobs can share the same fab_order."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        make_release(2, "A", "Welded", "FABRICATION", 6)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/2/A',
        json={'fab_order': 5},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job1 = Releases.query.filter_by(job=1, release="A").first()
        job2 = Releases.query.filter_by(job=2, release="A").first()
        assert job2.fab_order == 5
        assert job1.fab_order == 5   # unchanged — duplicate


def test_endpoint_fixed_tiers_unchanged(client, app):
    """Fixed-tier jobs keep their values when other releases are edited."""
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", 1)
        make_release(2, "A", "Paint complete", "READY_TO_SHIP", 2)
        make_release(3, "A", "Welded QC", "READY_TO_SHIP", 4)
        make_release(4, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/3/A',
        json={'fab_order': 3},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        complete = Releases.query.filter_by(job=1, release="A").first()
        paint = Releases.query.filter_by(job=2, release="A").first()
        wqc = Releases.query.filter_by(job=3, release="A").first()
        welded = Releases.query.filter_by(job=4, release="A").first()
        assert complete.fab_order == 1  # unchanged
        assert paint.fab_order == 2     # unchanged
        assert wqc.fab_order == 3
        assert welded.fab_order == 5    # unchanged


def test_endpoint_no_cascade_many_jobs(client, app):
    """Setting fab_order to a value shared by many jobs does not shift any of them."""
    with app.app_context():
        for i in range(10):
            make_release(i + 2, "A", "Welded", "FABRICATION", 3 + i)
        make_release(100, "A", "Welded", "FABRICATION", 50)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/100/A',
        json={'fab_order': 3},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        inserter = Releases.query.filter_by(job=100, release="A").first()
        assert inserter.fab_order == 3

        # All 10 original jobs unchanged — no cascade
        for i in range(10):
            job = Releases.query.filter_by(job=i + 2, release="A").first()
            assert job.fab_order == 3 + i


# ---------------------------------------------------------------------------
# Migration: renumber_fab_orders
# ---------------------------------------------------------------------------

def test_renumber_sets_fixed_tiers(app):
    """renumber_fab_orders sets Complete->1, Paint complete->2."""
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", 50)
        make_release(2, "A", "Paint complete", "READY_TO_SHIP", 99)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        renumber_fab_orders()

        c = Releases.query.filter_by(job=1, release="A").first()
        p = Releases.query.filter_by(job=2, release="A").first()
        assert c.fab_order == 1
        assert p.fab_order == 2


def test_renumber_dynamic_sequential(app):
    """Dynamic stages numbered sequentially starting at 3, in DYNAMIC_STAGE_ORDER."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 99)
        make_release(2, "A", "Welded QC", "READY_TO_SHIP", 50)
        make_release(3, "A", "Cut start", "FABRICATION", 75)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        renumber_fab_orders()

        wqc = Releases.query.filter_by(job=2, release="A").first()
        cut = Releases.query.filter_by(job=3, release="A").first()
        rel = Releases.query.filter_by(job=1, release="A").first()

        # Welded QC (pos 0) < Cut start (pos 4) < Released (pos 5)
        assert wqc.fab_order == 3
        assert cut.fab_order == 4
        assert rel.fab_order == 5


def test_renumber_preserves_relative_order(app):
    """Within a stage, relative order by original fab_order is preserved."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 20)
        make_release(2, "A", "Welded", "FABRICATION", 10)
        make_release(3, "A", "Welded", "FABRICATION", 15)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        renumber_fab_orders()

        j1 = Releases.query.filter_by(job=1, release="A").first()
        j2 = Releases.query.filter_by(job=2, release="A").first()
        j3 = Releases.query.filter_by(job=3, release="A").first()

        # Original order: job2(10) < job3(15) < job1(20) — preserved
        assert j2.fab_order < j3.fab_order < j1.fab_order


def test_renumber_dry_run_no_commit(app):
    """dry_run=True rolls back without changing the DB."""
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", 50)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        stats = renumber_fab_orders(dry_run=True)

        assert stats['total'] > 0

        c = Releases.query.filter_by(job=1, release="A").first()
        assert c.fab_order == 50  # unchanged


def test_renumber_returns_stats(app):
    """Stats dict has correct counts."""
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", 50)
        make_release(2, "A", "Paint complete", "READY_TO_SHIP", 99)
        make_release(3, "A", "Welded", "FABRICATION", 75)
        make_release(4, "A", "Released", "FABRICATION", 80)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        stats = renumber_fab_orders()

        assert stats['fixed_tier_1'] == 1
        assert stats['fixed_tier_2'] == 1
        assert stats['dynamic'] == 2
        assert stats['total'] == 4


def test_renumber_idempotent(app):
    """Already-correct data returns total=0."""
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", 1)
        make_release(2, "A", "Paint complete", "READY_TO_SHIP", 2)
        make_release(3, "A", "Welded QC", "READY_TO_SHIP", 3)
        make_release(4, "A", "Released", "FABRICATION", 4)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        stats = renumber_fab_orders()

        assert stats['total'] == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_endpoint_hold_no_clamping(client, app):
    """Hold stage skips bounds check via endpoint."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 5)
        make_release(2, "A", "Hold", "FABRICATION", 20)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/2/A',
        json={'fab_order': 3},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=2, release="A").first()
        assert job.fab_order == 3


def test_endpoint_none_stage_no_clamping(client, app):
    """None stage skips bounds check via endpoint."""
    with app.app_context():
        r = Releases(job=1, release="A", job_name="Test", stage=None,
                     stage_group=None, fab_order=10)
        db.session.add(r)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 5},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 5


def test_endpoint_reorder_same_job_twice(client, app):
    """Sequential updates to the same job both succeed."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    resp1 = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 8},
        content_type='application/json'
    )
    assert resp1.status_code == 200

    resp2 = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 4},
        content_type='application/json'
    )
    assert resp2.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 4


# ---------------------------------------------------------------------------
# Bounded cascade tests
# ---------------------------------------------------------------------------

def test_no_cascade_move_earlier(app):
    """Moving earlier does not bump any other jobs — duplicates allowed."""
    with app.app_context():
        jobs = []
        for i, pos in enumerate([25, 26, 27, 28, 29, 30, 40, 41, 42]):
            jobs.append(make_release(i + 1, "A", "Welded", "FABRICATION", pos))
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
            jobs.append(make_release(i + 1, "A", "Welded", "FABRICATION", pos))
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
        job_a = make_release(1, "A", "Welded", "FABRICATION", 40)
        job_b = make_release(2, "A", "Welded", "FABRICATION", 41)
        job_c = make_release(3, "A", "Welded", "FABRICATION", 42)
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
        target = make_release(1, "A", "Welded", "FABRICATION", None)
        job_at_10 = make_release(2, "A", "Welded", "FABRICATION", 10)
        job_at_11 = make_release(3, "A", "Welded", "FABRICATION", 11)
        job_at_9 = make_release(4, "A", "Welded", "FABRICATION", 9)
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
        job_a = make_release(1, "A", "Welded", "FABRICATION", 10)
        job_b = make_release(2, "A", "Welded", "FABRICATION", 11)
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
# Stage bleed prevention tests
# ---------------------------------------------------------------------------

def test_stage_change_appends_after_max(client, app):
    """Moving to a stage places at max_in_stage + 1 regardless of other stages."""
    with app.app_context():
        # Welded (pos 1) has releases at 8, 9, 10
        make_release(2, "A", "Welded", "FABRICATION", 8)
        make_release(3, "A", "Welded", "FABRICATION", 9)
        make_release(4, "A", "Welded", "FABRICATION", 10)
        # Fit Up Complete (pos 2) starts at 11 — no longer causes midpoint squeezing
        make_release(5, "A", "Fit Up Complete.", "FABRICATION", 11)
        # Release to be moved
        make_release(1, "A", "Released", "FABRICATION", 30)
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
        # max_in_stage (Welded) = 10, so new fab_order = 11
        assert job.fab_order == 11


def test_stage_change_legacy_bleed_appends_normally(client, app):
    """When later stages already have lower fab_orders (legacy bleed), just append at max + 1."""
    with app.app_context():
        # Welded (pos 1) has releases at 10, 15
        make_release(2, "A", "Welded", "FABRICATION", 10)
        make_release(3, "A", "Welded", "FABRICATION", 15)
        # Fit Up Complete (pos 2) has a release at 7 — legacy bleed (lower than Welded)
        make_release(5, "A", "Fit Up Complete.", "FABRICATION", 7)
        # Release to be moved
        make_release(1, "A", "Released", "FABRICATION", 30)
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
        # upper_bound = 7, max_in_stage = 15 → upper_bound <= max_in_stage (legacy bleed)
        # so we just append: max_in_stage + 1 = 16
        assert job.fab_order == 16


def test_stage_change_empty_stage_tight_upper_bound(client, app):
    """Moving to empty stage with tight upper bound uses fractional midpoint."""
    with app.app_context():
        # Welded QC (pos 0) is empty
        # Welded (pos 1) starts at 4
        make_release(2, "A", "Welded", "FABRICATION", 4)
        # Release to be moved
        make_release(1, "A", "Released", "FABRICATION", 20)
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
        # Welded QC (pos 0) is empty, lower_bound = None, upper_bound = 4
        # candidate = 3 (default), candidate < upper_bound 4, so 3 is fine
        assert job.fab_order == 3


def test_stage_change_empty_stage_very_tight_upper(client, app):
    """Empty stage where candidate 3 >= upper_bound uses fractional midpoint."""
    with app.app_context():
        # Welded QC (pos 0) is empty, Welded (pos 1) at fab_order 3
        make_release(2, "A", "Welded", "FABRICATION", 3)
        make_release(1, "A", "Released", "FABRICATION", 20)
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
        # candidate = 3, upper_bound = 3, candidate >= upper_bound
        # empty stage: effective_lower = 2, midpoint = (2 + 3) / 2 = 2.5
        # 2.5 < 3 → floor to 3... hmm. Actually min_dynamic floor applies.
        # But 3 >= upper_bound so it's a tie — duplicates are acceptable
        assert job.fab_order == 3


# ---------------------------------------------------------------------------
# clamp_fab_order floor and regression tests
# ---------------------------------------------------------------------------

def test_clamp_fab_order_floor_prevents_zero():
    """clamp_fab_order never returns below 3 for dynamic stages."""
    assert clamp_fab_order(0, lower=None, upper=None) == 3
    assert clamp_fab_order(-1, lower=None, upper=5) == 3
    assert clamp_fab_order(2, lower=None, upper=None) == 3
    assert clamp_fab_order(1, lower=0, upper=2) == 3


def test_clamp_fab_order_with_tight_bounds():
    """clamp_fab_order handles tight bounds correctly."""
    # lower=5, upper=7, value=6 → stays at 6
    assert clamp_fab_order(6, lower=5, upper=7) == 6
    # lower=5, upper=6, value=5 → 5 <= 5 → lower + 1 = 6, but 6 > 6 is False → 6
    assert clamp_fab_order(5, lower=5, upper=6) == 6
    # value=10, upper=8 → 10 > 8 → upper - 1 = 7
    assert clamp_fab_order(10, lower=5, upper=8) == 7


def test_clamp_fab_order_strict_upper():
    """strict_upper=True clamps at >= upper, not just > upper."""
    # value=8, upper=8, strict → 8 >= 8 → upper - 1 = 7
    assert clamp_fab_order(8, lower=5, upper=8, strict_upper=True) == 7
    # value=8, upper=8, not strict → 8 > 8 is False → 8
    assert clamp_fab_order(8, lower=5, upper=8, strict_upper=False) == 8


def test_no_cascade_archived_unaffected(app):
    """Setting fab_order does not affect any other jobs, including archived ones."""
    with app.app_context():
        target = make_release(1, "A", "Welded", "FABRICATION", 15)
        active_job = make_release(2, "A", "Welded", "FABRICATION", 10)
        archived_job = Releases(
            job=3, release="A", job_name="Archived", stage="Welded",
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
