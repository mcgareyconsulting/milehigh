"""
Tests for implicit stage ordering (fab_order clamping).

Covers:
- Pure utility functions (_normalize_stage, get_stage_position, clamp_fab_order)
- get_fab_order_bounds DB queries
- Integration: UpdateFabOrderCommand clamping
- Integration: stage change route clamping
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
    # "Cut Start" is stored in STAGE_TO_GROUP as-is but "Cut start" is also there.
    # _normalize_stage does exact match first; "Cut Start" is in STAGE_TO_GROUP so returns it.
    result = _normalize_stage("CUT START")
    assert result is not None
    assert result.lower() == "cut start"


def test_normalize_stage_unknown():
    assert _normalize_stage("Flying Saucer") is None


def test_normalize_stage_none():
    assert _normalize_stage(None) is None


def test_get_stage_position():
    assert get_stage_position("Released") == 0
    assert get_stage_position("Cut start") == 1
    assert get_stage_position("Material Ordered") == 2
    assert get_stage_position("Fit Up Complete.") == 3
    assert get_stage_position("Welded") == 4
    assert get_stage_position("Hold") is None
    assert get_stage_position("Shipping Complete") is None
    assert get_stage_position(None) is None


def test_get_stage_position_ready_to_ship():
    assert get_stage_position("Welded QC") == 0
    assert get_stage_position("Paint complete") == 1
    assert get_stage_position("Store at MHMW for shipping") == 2
    assert get_stage_position("Shipping planning") == 3


def test_clamp_below_lower():
    assert clamp_fab_order(5, lower=10, upper=None) == 11


def test_clamp_above_upper():
    assert clamp_fab_order(20, lower=None, upper=15) == 14


def test_clamp_in_range():
    assert clamp_fab_order(12, lower=10, upper=15) == 12


def test_clamp_no_bounds():
    assert clamp_fab_order(7, lower=None, upper=None) == 7


def test_clamp_at_lower_boundary():
    # value == lower → clamp to lower + 1
    assert clamp_fab_order(10, lower=10, upper=None) == 11


def test_clamp_at_upper_boundary():
    # value == upper, strict_upper=False (default) → no clamp (collision will handle it)
    assert clamp_fab_order(15, lower=None, upper=15) == 15


def test_clamp_at_upper_boundary_strict():
    # value == upper, strict_upper=True (stage change path) → clamp to upper - 1
    assert clamp_fab_order(15, lower=None, upper=15, strict_upper=True) == 14


def test_clamp_above_upper_strict():
    # value > upper, strict_upper=True → same result as default
    assert clamp_fab_order(20, lower=None, upper=15, strict_upper=True) == 14


# ---------------------------------------------------------------------------
# get_fab_order_bounds DB tests
# ---------------------------------------------------------------------------

def test_bounds_released_only_later_stages(app):
    """Released (pos=0): no earlier stages; upper=min of Welded jobs."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 50)
        make_release(2, "A", "Welded", "FABRICATION", 60)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Released", 99, "Z")
        assert lower is None
        assert upper == 50


def test_bounds_welded_only_earlier_stages(app):
    """Welded (pos=4): lower=max of Released jobs; no later stages."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 1)
        make_release(2, "A", "Released", "FABRICATION", 2)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Welded", 99, "Z")
        assert lower == 2
        assert upper is None


def test_bounds_cut_start_between_stages(app):
    """Cut start (pos=1): lower=max(Released), upper=min(Material Ordered onward)."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 1)
        make_release(2, "A", "Material Ordered", "FABRICATION", 5)
        make_release(3, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Cut start", 99, "Z")
        assert lower == 1
        assert upper == 5


def test_bounds_hold_exempt(app):
    """Hold is exempt — always returns (None, None)."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 5)
        make_release(2, "A", "Welded", "FABRICATION", 20)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Hold", 99, "Z")
        assert lower is None
        assert upper is None


def test_bounds_self_excluded(app):
    """Current job is excluded from the query."""
    with app.app_context():
        # Only job in the DB is the current job itself
        make_release(10, "A", "Released", "FABRICATION", 5)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Welded", 10, "A")
        # Released job is the current job — excluded → lower should be None
        assert lower is None
        assert upper is None


def test_bounds_variant_stage_name_matched(app):
    """DB stores 'Cut Start' (capital S) — variant should still be matched."""
    with app.app_context():
        # Store with variant name
        make_release(1, "A", "Cut Start", "FABRICATION", 3)
        make_release(2, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

        lower, upper = get_fab_order_bounds("Material Ordered", 99, "Z")
        assert lower == 3   # Cut Start variant matched
        assert upper == 10


# ---------------------------------------------------------------------------
# Integration: UpdateFabOrderCommand clamping
# ---------------------------------------------------------------------------

def test_fab_order_clamped_above_later_stage(app):
    """Released job tries fab_order=60 when Welded is at 50 → stored as 49."""
    with app.app_context():
        released = make_release(1, "A", "Released", "FABRICATION", 1)
        make_release(2, "A", "Welded", "FABRICATION", 50)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=60)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(released)
        assert released.fab_order == 49


def test_fab_order_clamped_below_earlier_stage(app):
    """Welded job tries fab_order=0 when Released is at 10 → stored as 11."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 10)
        welded = make_release(2, "A", "Welded", "FABRICATION", 40)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=2, release="A", fab_order=0)
        with patch('app.services.outbox_service.OutboxService.add'):
            result = cmd.execute()

        db.session.refresh(welded)
        assert welded.fab_order == 11


def test_hold_not_clamped(app):
    """Hold job ignores bounds entirely."""
    with app.app_context():
        released = make_release(1, "A", "Released", "FABRICATION", 5)
        hold_job = make_release(2, "A", "Hold", "FABRICATION", None)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=2, release="A", fab_order=1)
        result = cmd.execute()

        db.session.refresh(hold_job)
        # Should be stored as-is (no clamping) — value 1 is below Released at 5
        # but Hold is exempt; collision detection may bump Released, that's fine
        assert hold_job.fab_order == 1


def test_in_range_unchanged(app):
    """Value within valid range → no clamp, no collision cascade from boundaries."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 1)
        cut_start = make_release(2, "A", "Cut start", "FABRICATION", 5)
        make_release(3, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=2, release="A", fab_order=5)
        result = cmd.execute()

        db.session.refresh(cut_start)
        assert cut_start.fab_order == 5


# ---------------------------------------------------------------------------
# Integration: stage change route clamping
# ---------------------------------------------------------------------------

def test_stage_change_triggers_clamp(client, app):
    """Released job at fab_order=20 moves to Cut start when Welded is at 5 → clamped to 4.

    Cut start (pos=1) upper bound = min(Material Ordered...Welded) = 5.
    Since 20 >= 5, clamps to 5 - 1 = 4.
    """
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 20)
        make_release(2, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Cut start'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        # upper bound for Cut start = min(Welded) = 5 → clamped to 5 - 1 = 4
        assert job.fab_order == 4


def test_stage_change_same_group_no_clamp_needed(client, app):
    """Cut start at fab_order=8 moves to Material Ordered; bounds allow 8 → unchanged."""
    with app.app_context():
        make_release(1, "A", "Cut start", "FABRICATION", 8)
        make_release(2, "A", "Released", "FABRICATION", 1)
        make_release(3, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Material Ordered'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        # bounds for Material Ordered: lower=max(Released,Cut start excluding self)=1, upper=min(Welded)=10
        # 8 is in range → unchanged
        assert job.fab_order == 8


def test_fab_to_ready_to_ship_unaffected(client, app):
    """Existing FABRICATION→READY_TO_SHIP logic still assigns max+1 correctly."""
    with app.app_context():
        make_release(1, "A", "Welded", "FABRICATION", 5)
        make_release(2, "A", "Welded QC", "READY_TO_SHIP", 3)
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
        # max in READY_TO_SHIP = 3, so new fab_order = 4
        assert job.fab_order == 4


# ---------------------------------------------------------------------------
# Section A: Boundary behavior (>= vs > upper bound)
# ---------------------------------------------------------------------------

def test_clamp_at_upper_boundary_with_collision(app):
    """Released A tries fab_order=5, Welded B is at 5.
    With strict_upper=False (command path): no clamp; collision bumps Welded to 6.
    Final: Released=5, Welded=6.
    """
    with app.app_context():
        released = make_release(1, "A", "Released", "FABRICATION", 1)
        welded = make_release(2, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(released)
        db.session.refresh(welded)
        assert released.fab_order == 5
        assert welded.fab_order == 6


def test_clamp_above_upper_with_collision(app):
    """Released A tries fab_order=10, Welded B is at 5.
    10 > 5 → clamped to 4. Collision bumps Welded from 5 to 6 (Welded >= clamped value 4).
    Final: Released=4, Welded=6.
    """
    with app.app_context():
        released = make_release(1, "A", "Released", "FABRICATION", 1)
        welded = make_release(2, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=10)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(released)
        db.session.refresh(welded)
        assert released.fab_order == 4
        assert welded.fab_order == 6


def test_lower_bound_same_position_always_clamped(app):
    """Welded B tries to move to position 10 (same as Released A).
    Lower bound clamp must fire: 10 <= 10 → clamped to 11.
    (Allowing same-position would let collision bump Released UP → intermingling.)
    """
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 10)
        welded = make_release(2, "A", "Welded", "FABRICATION", 15)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=2, release="A", fab_order=10)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(welded)
        assert welded.fab_order == 11


def test_clamp_strict_upper_for_stage_change(client, app):
    """Released A at fab_order=5 moves to Cut start when another job is Welded at 5.
    Stage change path uses strict_upper=True: 5 >= 5 → clamped to 4.
    """
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 5)
        make_release(2, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

    with patch('app.brain.job_log.routes.get_list_id_by_stage', return_value=None):
        resp = client.patch(
            '/brain/update-stage/1/A',
            json={'stage': 'Cut start'},
            content_type='application/json'
        )

    assert resp.status_code == 200

    with app.app_context():
        job = Releases.query.filter_by(job=1, release="A").first()
        assert job.fab_order == 4


# ---------------------------------------------------------------------------
# Section B: Cascade correctness
# ---------------------------------------------------------------------------

def test_cascade_bumped_cut_start_stays_below_welded(app):
    """Released=1, Cut start=9, Welded=10. Set Released to 9.
    Released clamped: upper=min(Cut start,Welded)=9, but 9 is not > 9 so no clamp → stays 9.
    Collision bumps Cut start from 9→10, then Welded from 10→11.
    Final: Released=9, Cut start=10, Welded=11; ordering maintained.
    """
    with app.app_context():
        released = make_release(1, "A", "Released", "FABRICATION", 1)
        cut_start = make_release(2, "A", "Cut start", "FABRICATION", 9)
        welded = make_release(3, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=9)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(released)
        db.session.refresh(cut_start)
        db.session.refresh(welded)
        assert released.fab_order < cut_start.fab_order
        assert cut_start.fab_order < welded.fab_order


def test_full_chain_ordering_preserved(app):
    """Released=1, Cut start=5, Material Ordered=8, Welded=10. Set Released to 5.
    After collision cascade, ordering Released < Cut start < Material Ordered < Welded must hold.
    """
    with app.app_context():
        released = make_release(1, "A", "Released", "FABRICATION", 1)
        cut_start = make_release(2, "A", "Cut start", "FABRICATION", 5)
        mat_ordered = make_release(3, "A", "Material Ordered", "FABRICATION", 8)
        welded = make_release(4, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(released)
        db.session.refresh(cut_start)
        db.session.refresh(mat_ordered)
        db.session.refresh(welded)
        assert released.fab_order < cut_start.fab_order
        assert cut_start.fab_order < mat_ordered.fab_order
        assert mat_ordered.fab_order < welded.fab_order


def test_multiple_releases_and_welded(app):
    """Released A=1, Released B=2, Welded=5. Set Released A to 5.
    A lands at 5; collision bumps Welded. A and B always < Welded.
    """
    with app.app_context():
        rel_a = make_release(1, "A", "Released", "FABRICATION", 1)
        rel_b = make_release(2, "A", "Released", "FABRICATION", 2)
        welded = make_release(3, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(rel_a)
        db.session.refresh(rel_b)
        db.session.refresh(welded)
        assert rel_a.fab_order == 5
        assert rel_a.fab_order < welded.fab_order
        assert rel_b.fab_order < welded.fab_order


# ---------------------------------------------------------------------------
# Section C: Pre-existing intermingling corrected
# ---------------------------------------------------------------------------

def test_intermingling_corrected_on_update(app):
    """Released A=50 (wrong — above Welded B=5). Set Released A to 20.
    Upper bound for Released = min(Welded) = 5. 20 > 5 → clamped to 4.
    Collision bumps Welded from 5 → 5 (not triggered since clamped value 4 < 5).
    Final: Released=4, Welded=5; A < B.
    """
    with app.app_context():
        released = make_release(1, "A", "Released", "FABRICATION", 50)
        welded = make_release(2, "A", "Welded", "FABRICATION", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=20)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(released)
        db.session.refresh(welded)
        assert released.fab_order < welded.fab_order


def test_intermingling_not_worsened_by_unrelated_update(app):
    """Released A=1, Released B=50 (bad), Welded C=10. Set Released A to 2.
    A is within bounds → no clamp. B and C unchanged. A < C even if B is still bad.
    """
    with app.app_context():
        rel_a = make_release(1, "A", "Released", "FABRICATION", 1)
        rel_b = make_release(2, "A", "Released", "FABRICATION", 50)
        welded = make_release(3, "A", "Welded", "FABRICATION", 10)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=2)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(rel_a)
        db.session.refresh(rel_b)
        db.session.refresh(welded)
        assert rel_a.fab_order == 2
        assert rel_a.fab_order < welded.fab_order


# ---------------------------------------------------------------------------
# Section D: READY_TO_SHIP group parity
# ---------------------------------------------------------------------------

def test_ready_to_ship_clamp_above_later_stage(app):
    """Welded QC=1, Shipping planning=5. Set Welded QC to 10.
    10 > 5 → clamped to 4.
    """
    with app.app_context():
        welded_qc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 1)
        make_release(2, "A", "Shipping planning", "READY_TO_SHIP", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=10)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(welded_qc)
        assert welded_qc.fab_order == 4


def test_ready_to_ship_at_exact_later_position(app):
    """Welded QC=1, Shipping planning=5. Set Welded QC to 5.
    5 is not > 5 (strict_upper=False default) → no clamp. Collision bumps Shipping planning to 6.
    Final: Welded QC=5, Shipping planning=6.
    """
    with app.app_context():
        welded_qc = make_release(1, "A", "Welded QC", "READY_TO_SHIP", 1)
        shipping = make_release(2, "A", "Shipping planning", "READY_TO_SHIP", 5)
        db.session.commit()

        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        cmd = UpdateFabOrderCommand(job_id=1, release="A", fab_order=5)
        with patch('app.services.outbox_service.OutboxService.add'):
            cmd.execute()

        db.session.refresh(welded_qc)
        db.session.refresh(shipping)
        assert welded_qc.fab_order == 5
        assert shipping.fab_order == 6
