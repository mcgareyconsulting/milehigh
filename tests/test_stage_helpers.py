"""Pure-helper tests for fab_order ordering — no DB, no Flask."""
from app.api.helpers import (
    _normalize_stage,
    get_stage_position,
    clamp_fab_order,
    get_fixed_tier,
    STAGE_TO_GROUP,
    STAGE_HOUR_PERCENTAGES,
    STAGE_PROGRESSION_RANK,
    FIXED_TIER_STAGES,
)


def test_normalize_stage_exact():
    assert _normalize_stage("Cut Start") == "Cut Start"


def test_normalize_stage_case_insensitive_fallback():
    # Case-insensitive fallback absorbs incidental drift even after canonicalization.
    result = _normalize_stage("CUT START")
    assert result == "Cut Start"


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
    assert get_stage_position("Fitup Complete") == 4
    assert get_stage_position("Fitup Start") == 5
    assert get_stage_position("Cut Complete") == 6
    assert get_stage_position("Cut Start") == 7
    assert get_stage_position("Material Ordered") == 8
    assert get_stage_position("Released") == 9


def test_get_stage_position_fixed_tiers_return_none():
    """Fixed-tier stages are not in the dynamic order."""
    assert get_stage_position("Ship Complete") is None
    assert get_stage_position("Install Start") is None
    assert get_stage_position("Install Complete") is None
    assert get_stage_position("Complete") is None
    assert get_stage_position("Paint Complete") is None
    assert get_stage_position("Store at MHMW") is None
    assert get_stage_position("Ship Planning") is None


def test_get_stage_position_hold_exempt():
    assert get_stage_position("Hold") is None


def test_get_stage_position_none():
    assert get_stage_position(None) is None


def test_get_fixed_tier():
    """Fixed-tier stages return their tier value."""
    # Tier 0 — the new post-shipping installation stages
    assert get_fixed_tier("Install Start") == 0
    assert get_fixed_tier("Install Complete") == 0
    # Tier 1 — Ship Complete only
    assert get_fixed_tier("Ship Complete") == 1
    # Complete is intentionally not in any tier — it holds fab_order=NULL.
    assert get_fixed_tier("Complete") is None
    # Tier 2 — Paint Complete + the in-shop shipping holds
    assert get_fixed_tier("Paint Complete") == 2
    assert get_fixed_tier("Store at MHMW") == 2
    assert get_fixed_tier("Ship Planning") == 2


def test_get_fixed_tier_dynamic_stages_return_none():
    """Dynamic stages are not fixed tiers."""
    assert get_fixed_tier("Released") is None
    assert get_fixed_tier("Cut Start") is None
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


# ---------------------------------------------------------------------------
# Canonical taxonomy integrity (catches drift between the three tables)
# ---------------------------------------------------------------------------

def test_install_stages_in_complete_group():
    """Install Start and Install Complete are part of the COMPLETE stage_group."""
    assert STAGE_TO_GROUP["Install Start"] == "COMPLETE"
    assert STAGE_TO_GROUP["Install Complete"] == "COMPLETE"


def test_install_stages_in_tier_zero():
    """Install Start and Install Complete share fab_order tier 0 (post-shipping)."""
    assert get_fixed_tier("Install Start") == 0
    assert get_fixed_tier("Install Complete") == 0
    assert FIXED_TIER_STAGES[0] == ["Install Start", "Install Complete"]


def test_stage_hour_percentages_covers_every_stage():
    """Every stage in STAGE_TO_GROUP must have a hours-percentage entry."""
    diff = set(STAGE_TO_GROUP.keys()) ^ set(STAGE_HOUR_PERCENTAGES.keys())
    assert not diff, f"STAGE_HOUR_PERCENTAGES drift vs STAGE_TO_GROUP: {diff}"


def test_stage_hour_percentages_values_are_well_formed():
    """Every entry has fab and install keys with values in [0, 100]."""
    for stage, pct in STAGE_HOUR_PERCENTAGES.items():
        assert set(pct.keys()) == {"fab", "install"}, f"{stage}: bad keys {pct}"
        assert 0 <= pct["fab"] <= 100, f"{stage}: fab {pct['fab']} out of range"
        assert 0 <= pct["install"] <= 100, f"{stage}: install {pct['install']} out of range"


def test_stage_progression_rank_covers_every_stage():
    """STAGE_PROGRESSION_RANK has an entry for every stage_group key."""
    missing = set(STAGE_TO_GROUP.keys()) - set(STAGE_PROGRESSION_RANK.keys())
    assert not missing, f"Missing rank entries: {missing}"


def test_install_stages_have_zero_fab_remaining():
    """Past fab — both install stages report 0% fab remaining."""
    assert STAGE_HOUR_PERCENTAGES["Install Start"]["fab"] == 0
    assert STAGE_HOUR_PERCENTAGES["Install Complete"]["fab"] == 0


def test_install_start_consumes_half_install_hours():
    """Per the client matrix, Install Start = 50% install hours remaining."""
    assert STAGE_HOUR_PERCENTAGES["Install Start"]["install"] == 50


def test_no_legacy_variants_in_canonical_dicts():
    """Catches accidental reintroduction of variant spellings."""
    legacy = {
        "Cut start", "Fit Up Complete.", "Fit up Comp", "Fitup comp",
        "Paint complete", "Paint comp", "Store at Shop",
        "Store at MHMW for shipping",
        "Shipping planning", "Shipping Planning",
        "Shipping completed", "Shipping Complete",
        "WeldingQC", "Welding QC",
    }
    intersect = legacy & set(STAGE_TO_GROUP.keys())
    assert not intersect, f"Legacy variants leaked back into STAGE_TO_GROUP: {intersect}"

