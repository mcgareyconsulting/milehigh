"""
Tests for unified fab_order ordering — DB-level and route-level.

Covers:
- get_fab_order_bounds DB queries (unified across all dynamic stages)
- Stage-change route fixed-tier and dynamic assignment
- PATCH /brain/update-fab-order endpoint: happy path, validation, collision
- renumber_fab_orders migration helper
- Edge cases (HOLD, none stage, reorder)
- Stage bleed prevention

Pure-helper tests live in test_stage_helpers.py.
UpdateFabOrderCommand integration tests live in test_fab_order_command.py.
"""
import pytest
from unittest.mock import patch

from app.models import Releases, db
from app.api.helpers import (
    _get_all_variants_for_stages,
    get_fab_order_bounds,
    DYNAMIC_STAGE_ORDER,
    FIXED_TIER_STAGES,
)


# ---------------------------------------------------------------------------
# Fixtures (app, client, mock_admin_user are in tests/conftest.py)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch('app.auth.utils.get_current_user', return_value=mock_admin_user):
        yield


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
# get_fab_order_bounds DB tests (unified across all dynamic stages)
# ---------------------------------------------------------------------------

def test_bounds_welded_qc_no_earlier_stages(app):
    """Welded QC (pos=0): no earlier dynamic stages; upper=min of Welded jobs."""
    with app.app_context():
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
        make_release(2, "A", "Weld Complete", "FABRICATION", 15)
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

        lower, upper = get_fab_order_bounds("Weld Complete", 99, "Z")
        assert lower == 5   # max of Welded QC
        assert upper == 20  # min of Fit Up Complete


def test_bounds_cross_group_unified(app):
    """Bounds work across old stage_groups — Welded QC and Welded are neighbors."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Fit Up Complete.", "FABRICATION", 15)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Weld Complete", 99, "Z")
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

        lower, upper = get_fab_order_bounds("Weld Complete", 10, "A")
        assert lower is None
        assert upper is None


# ---------------------------------------------------------------------------
# Integration: stage change route
# ---------------------------------------------------------------------------

def test_stage_change_to_complete_clears_fab_order(client, app):
    """Moving to Complete clears fab_order to NULL and cascades job_comp='X'."""
    with app.app_context():
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
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
        assert job.fab_order is None
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


def test_stage_change_to_dynamic_preserves_fab_order(client, app):
    """Moving between Fabrication-group stages leaves fab_order untouched."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 20)
        make_release(2, "A", "Weld Complete", "FABRICATION", 5)
        make_release(3, "A", "Weld Complete", "FABRICATION", 6)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Weld Complete'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 20


def test_stage_change_to_welded_qc_empty_paint_deck_bumps_to_3(client, app):
    """Fab → Welded QC with empty paint deck: lands at 3 (floor above tiers 1-2)."""
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
        assert job.fab_order == 3


def test_stage_change_to_welded_qc_bumps_to_back_of_paint_deck(client, app):
    """Fab → Welded QC lands at max(WQC + Paint Start) + 1, not preserving the old fab_order."""
    with app.app_context():
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
        # No other R2S items → floor=2, +1=3
        assert job.fab_order == 3


def test_stage_change_to_welded_qc_with_existing_paint_deck(client, app):
    """Fab → Welded QC with WQC=5, Paint Start=7, plus a fab item at 4 → bump to 8 (only R2S counted)."""
    with app.app_context():
        make_release(1, "A", "Weld Complete", "FABRICATION", 4)
        make_release(2, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(3, "A", "Paint Start", "READY_TO_SHIP", 7)
        make_release(4, "A", "Released", "FABRICATION", 30)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/4/A',
            json={'stage': 'Welded QC'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=4, release="A").first()
        assert job.fab_order == 8


def test_stage_change_paint_start_to_welded_qc_preserves_fab_order(client, app):
    """Already in R2S (Paint Start → Welded QC): backwards move preserves fab_order."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Paint Start", "READY_TO_SHIP", 7)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/2/A',
            json={'stage': 'Welded QC'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=2, release="A").first()
        assert job.fab_order == 7


def test_stage_change_welded_qc_resave_preserves_fab_order(client, app):
    """Re-saving a Welded QC release as Welded QC does not bump it."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Welded QC", "READY_TO_SHIP", 9)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        # Re-save job 1 (currently at fab_order=5) as Welded QC.
        # If the bump fired, it would jump to 10 (max=9 + 1).
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Welded QC'},
            content_type='application/json'
        )

    # The same-stage write may dedup at the event layer; whether it returns
    # 200 or a dedup status, the fab_order MUST not change.
    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 5


def test_stage_change_to_welded_qc_collision_with_fab_min_allowed(client, app):
    """Bump landing at min(FAB) is allowed — no clamp, duplicates across stages OK."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 9)
        make_release(2, "A", "Weld Complete", "FABRICATION", 10)
        make_release(3, "A", "Released", "FABRICATION", 30)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        # Job 3 (FAB, fab_order=30) → Welded QC. Bump = max(WQC=9) + 1 = 10,
        # which equals job 2's fab_order in fabrication. Allowed.
        resp = client.patch(
            '/brain/update-stage/3/A',
            json={'stage': 'Welded QC'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        moved = Releases.query.filter_by(job=3, release="A").first()
        fab_neighbor = Releases.query.filter_by(job=2, release="A").first()
        assert moved.fab_order == 10
        assert fab_neighbor.fab_order == 10  # unchanged — collision permitted


def test_stage_change_to_shipping_planning_sets_tier_2(client, app):
    """Shipping planning is a fixed tier 2 stage."""
    with app.app_context():
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
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


def test_endpoint_fab_order_negative_accepted(client, app):
    """Negative fab_order is accepted as-is for non-fixed-tier stages."""
    with app.app_context():
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': -5},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == -5


def test_endpoint_fab_order_zero_accepted(client, app):
    """Zero fab_order is accepted as-is for non-fixed-tier stages."""
    with app.app_context():
        make_release(1, "A", "Weld Complete", "FABRICATION", 10)
        db.session.commit()

    resp = client.patch(
        '/brain/update-fab-order/1/A',
        json={'fab_order': 0},
        content_type='application/json'
    )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 0


def test_endpoint_fab_order_very_large_accepted(client, app):
    """Very large fab_order is accepted — no stage bounds clamping."""
    with app.app_context():
        make_release(1, "A", "Welded QC", "READY_TO_SHIP", 5)
        make_release(2, "A", "Weld Complete", "FABRICATION", 10)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
        make_release(2, "A", "Weld Complete", "FABRICATION", 6)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 3)
        make_release(2, "A", "Weld Complete", "FABRICATION", 5)
        make_release(3, "A", "Weld Complete", "FABRICATION", 6)
        make_release(4, "A", "Weld Complete", "FABRICATION", 7)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 3)
        make_release(2, "A", "Weld Complete", "FABRICATION", 5)
        make_release(3, "A", "Weld Complete", "FABRICATION", 8)
        make_release(4, "A", "Weld Complete", "FABRICATION", 12)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
        make_release(2, "A", "Weld Complete", "FABRICATION", 6)
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
        make_release(4, "A", "Weld Complete", "FABRICATION", 5)
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
            make_release(i + 2, "A", "Weld Complete", "FABRICATION", 3 + i)
        make_release(100, "A", "Weld Complete", "FABRICATION", 50)
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
    """renumber_fab_orders clears Complete to NULL, Shipping completed->1, Paint complete->2."""
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", 50)
        make_release(2, "A", "Paint complete", "READY_TO_SHIP", 99)
        make_release(3, "A", "Shipping completed", "COMPLETE", 88)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        renumber_fab_orders()

        c = Releases.query.filter_by(job=1, release="A").first()
        p = Releases.query.filter_by(job=2, release="A").first()
        s = Releases.query.filter_by(job=3, release="A").first()
        assert c.fab_order is None
        assert p.fab_order == 2
        assert s.fab_order == 1


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
        make_release(1, "A", "Weld Complete", "FABRICATION", 20)
        make_release(2, "A", "Weld Complete", "FABRICATION", 10)
        make_release(3, "A", "Weld Complete", "FABRICATION", 15)
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
        # Stage='Complete' starts with a stale fab_order=50; should be cleared to NULL.
        make_release(1, "A", "Complete", "COMPLETE", 50)
        make_release(2, "A", "Paint complete", "READY_TO_SHIP", 99)
        make_release(3, "A", "Weld Complete", "FABRICATION", 75)
        make_release(4, "A", "Released", "FABRICATION", 80)
        # Add a Shipping completed so fixed_tier_1 has something to renumber.
        make_release(5, "A", "Shipping completed", "COMPLETE", 88)
        db.session.commit()

        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders
        stats = renumber_fab_orders()

        assert stats['complete_cleared'] == 1
        assert stats['fixed_tier_1'] == 1
        assert stats['fixed_tier_2'] == 1
        assert stats['dynamic'] == 2
        assert stats['total'] == 5

        # Verify Complete actually had its fab_order cleared.
        c = Releases.query.filter_by(job=1, release="A").first()
        assert c.fab_order is None


def test_renumber_idempotent(app):
    """Already-correct data returns total=0."""
    with app.app_context():
        # Stage='Complete' is correct only when fab_order is NULL.
        make_release(1, "A", "Complete", "COMPLETE", None)
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
        make_release(1, "A", "Weld Complete", "FABRICATION", 5)
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
# Stage bleed prevention tests
# ---------------------------------------------------------------------------

def test_stage_change_between_fabrication_stages_preserves_fab_order(client, app):
    """Stage change across Fabrication-group stages never modifies fab_order."""
    with app.app_context():
        make_release(2, "A", "Weld Complete", "FABRICATION", 8)
        make_release(3, "A", "Weld Complete", "FABRICATION", 9)
        make_release(4, "A", "Weld Complete", "FABRICATION", 10)
        make_release(5, "A", "Fit Up Complete.", "FABRICATION", 11)
        make_release(1, "A", "Released", "FABRICATION", 30)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Weld Complete'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 30

