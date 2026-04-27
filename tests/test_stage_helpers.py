"""Pure-helper tests for fab_order ordering — no DB, no Flask."""
from app.api.helpers import (
    _normalize_stage,
    get_stage_position,
    clamp_fab_order,
    get_fixed_tier,
)


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
    assert get_stage_position("Fit Up Complete.") == 4
    assert get_stage_position("Fitup Start") == 5
    assert get_stage_position("Cut Complete") == 6
    assert get_stage_position("Cut start") == 7
    assert get_stage_position("Material Ordered") == 8
    assert get_stage_position("Released") == 9


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
    # Complete is intentionally not in any tier — it holds fab_order=NULL.
    assert get_fixed_tier("Complete") is None
    assert get_fixed_tier("Paint complete") == 2
    assert get_fixed_tier("Paint Complete") == 2
    assert get_fixed_tier("Store at MHMW for shipping") == 2
    assert get_fixed_tier("Shipping planning") == 2


def test_get_fixed_tier_dynamic_stages_return_none():
    """Dynamic stages are not fixed tiers."""
    assert get_fixed_tier("Released") is None
    assert get_fixed_tier("Cut start") is None
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

