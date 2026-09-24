"""T13: the stage_group axis is the department axis, and the photo gate reads it.

Pure unit tests on the mapping constants in app.api.helpers and the gate rule in
features/stage/gate.py — no DB, no Flask. The rule's table is the one exercised by
hand on 2026-09-23; keeping it here is what stops a future STAGE_TO_GROUP edit from
silently moving a gate.
"""
import pytest

from app.api.helpers import (
    GATE_ENTRY_STAGE,
    STAGE_GROUP_ORDER,
    STAGE_ORDER,
    STAGE_TO_GROUP,
    get_stage_group_from_stage,
)
from app.brain.job_log.features.stage.gate import (
    StagePhotoRequiredError,
    gate_stage_for,
)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("old,new,expected", [
    # Fab → Paint
    ("Weld Complete", "Welded QC", "Welded QC"),
    ("Hold", "Welded QC", "Welded QC"),
    # inside Paint, either direction
    ("Paint Start", "Welded QC", None),
    ("Welded QC", "Paint Start", None),
    # Paint → Ship, including a jump past the entry stage
    ("Paint Start", "Paint Complete", "Paint Complete"),
    ("Welded QC", "Store at MHMW", "Paint Complete"),
    # inside Ready to Ship
    ("Store at MHMW", "Ship Planning", None),
    # Ship → Install, including jumps past the entry stage
    ("Ship Planning", "Ship Complete", "Ship Complete"),
    ("Ship Planning", "Complete", "Ship Complete"),
    ("Paint Complete", "Ship Complete", "Ship Complete"),
    # multi-department jumps owe the destination's gate only
    ("Weld Complete", "Ship Complete", "Ship Complete"),
    ("Released", "Complete", "Ship Complete"),
    # backward never gates
    ("Ship Complete", "Ship Planning", None),
    ("Complete", "Released", None),
    # inside Fab / inside Complete
    ("Cut Start", "Fitup Start", None),
    ("Ship Complete", "Install Start", None),
    # unclassifiable on either side
    (None, "Welded QC", None),
    ("Weld Complete", "Bogus", None),
])
def test_gate_stage_for(old, new, expected):
    assert gate_stage_for(old, new) == expected


# ---------------------------------------------------------------------------
# The mapping the rule reads
# ---------------------------------------------------------------------------

def test_every_group_value_is_in_shop_order():
    assert set(STAGE_TO_GROUP.values()) == set(STAGE_GROUP_ORDER)
    assert STAGE_GROUP_ORDER == ["FABRICATION", "PAINT", "READY_TO_SHIP", "COMPLETE"]


def test_gate_entry_stages_open_their_own_group():
    assert set(GATE_ENTRY_STAGE) == set(STAGE_GROUP_ORDER) - {"FABRICATION"}
    for group, stage in GATE_ENTRY_STAGE.items():
        assert STAGE_TO_GROUP[stage] == group, (group, stage)


def test_legacy_stage_order_matches_the_mapping():
    for group, stages in STAGE_ORDER.items():
        mapped = {s for s, g in STAGE_TO_GROUP.items() if g == group}
        # STAGE_ORDER omits Hold on purpose (STAGE_ORDER_EXEMPT); everything else agrees.
        assert set(stages) == mapped - {"Hold"}, group
    assert STAGE_ORDER["PAINT"] == ["Welded QC", "Paint Start"]
    assert STAGE_ORDER["READY_TO_SHIP"] == ["Paint Complete", "Store at MHMW", "Ship Planning"]


def test_paint_stages_map_to_paint():
    assert get_stage_group_from_stage("Welded QC") == "PAINT"
    assert get_stage_group_from_stage("Paint Start") == "PAINT"
    assert get_stage_group_from_stage("welded qc") == "PAINT"   # case-insensitive fallback
    assert get_stage_group_from_stage("Paint Complete") == "READY_TO_SHIP"


def test_command_exposes_the_derived_gate_set():
    from app.brain.job_log.features.stage.command import (
        STAGE_PHOTO_GATE_ENABLED,
        STAGE_PHOTO_GATES,
    )
    assert STAGE_PHOTO_GATE_ENABLED is True
    assert set(STAGE_PHOTO_GATES) == {"Welded QC", "Paint Complete", "Ship Complete"}


# ---------------------------------------------------------------------------
# The error the gate raises
# ---------------------------------------------------------------------------

def test_error_names_both_stages():
    err = StagePhotoRequiredError("Ship Complete", requested_stage="Complete")
    assert err.stage == "Ship Complete"
    assert err.requested_stage == "Complete"
    assert "Ship Complete" in str(err) and "Complete" in str(err)


def test_error_defaults_requested_stage_to_the_gate():
    err = StagePhotoRequiredError("Welded QC")
    assert err.requested_stage == "Welded QC"
