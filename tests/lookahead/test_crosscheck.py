"""Cross-check engine tests, pinned to the REAL Alta Metro data.

Fixtures are the actual job-560 releases/submittals pulled from prod (2026-07-20) and the
metal activities the parser extracts from AMC - 3WK Lookahead - 07172026.pdf. This locks the
engine to the ground truth: Bldg C steel slips 3 days, Bldg D steel is still in drafting,
the combined B-D embed release covers both buildings.
"""
from datetime import date

from app.brain.lookahead import crosscheck as cc


# --- real job-560 records (subset that matters for the metal cross-check) ---
RELEASES = [
    {"release": "941", "description": "Bld B Structrual Steel", "stage": "Released",
     "start_install": date(2026, 8, 28), "comp_eta": date(2026, 9, 1)},
    {"release": "923", "description": "Bld C Structural Steel", "stage": "Released",
     "start_install": date(2026, 7, 24), "comp_eta": date(2026, 7, 30)},
    {"release": "459", "description": "Bld A Structural Embeds", "stage": "Complete",
     "job_comp": "X", "start_install": date(2026, 4, 7)},
    {"release": "526", "description": "Bld B-D Structural Embeds", "stage": "Complete",
     "job_comp": "X", "start_install": date(2026, 4, 28)},
]
SUBMITTALS = [
    {"rel": 944, "title": "Building D Structural Steel",
     "type": "Drafting Release Review", "status": "Open"},
    {"rel": 923, "title": "Building C Structural Steel",
     "type": "Drafting Release Review", "status": "Closed"},
]

# The 6 metal activities the parser pulls from the 7/17 lookahead.
ACTIVITIES = [
    {"wbs_id": 1048, "building": "Building B", "task_name": "Embed Install / Drains Set", "start": date(2026, 8, 3)},
    {"wbs_id": 1049, "building": "Building B", "task_name": "Anchor Bolt Install & Hold-Down Verification", "start": date(2026, 8, 3)},
    {"wbs_id": 1888, "building": "Building C", "task_name": "Structural Steel", "start": date(2026, 7, 21)},
    {"wbs_id": 2662, "building": "Building D", "task_name": "Embed Install / Drains Set", "start": date(2026, 7, 27)},
    {"wbs_id": 2663, "building": "Building D", "task_name": "Anchor Bolt Install & Hold-Down Verification", "start": date(2026, 7, 27)},
    {"wbs_id": 2668, "building": "Building D", "task_name": "Structural Steel", "start": date(2026, 8, 4)},
]


def by_wbs(results):
    return {r["wbs_id"]: r for r in results}


# --- matching primitives ---

def test_buildings_of_handles_combined_range():
    assert cc.buildings_of("Bld B-D Structural Embeds") == {"B", "C", "D"}
    assert cc.buildings_of("Bld C Structural Steel") == {"C"}
    assert cc.buildings_of("Building D Structural Steel") == {"D"}


def test_scope_family():
    assert cc.scope_of("Bld C Structural Steel") == cc.STEEL
    assert cc.scope_of("Bld B-D Structural Embeds") == cc.EMBED
    assert cc.scope_of("Anchor Bolt Install & Hold-Down Verification") == cc.EMBED


# --- the ground-truth cross-check ---

def test_bldg_c_steel_slips_three_days():
    r = by_wbs(cc.cross_check(ACTIVITIES, RELEASES, SUBMITTALS))[1888]
    assert r["matched_kind"] == "release"
    assert r["matched_ref"] == "923"
    assert r["gc_need"] == date(2026, 7, 21)
    assert r["our_date"] == date(2026, 7, 24)
    assert r["slip_days"] == 3
    assert r["status"] == cc.STATUS_SLIP


def test_bldg_d_steel_is_still_in_drafting():
    r = by_wbs(cc.cross_check(ACTIVITIES, RELEASES, SUBMITTALS))[2668]
    assert r["matched_kind"] == "submittal"   # DRR 944, no release yet
    assert r["matched_ref"] == 944
    assert r["status"] == cc.STATUS_IN_DRAFTING
    assert r["severity"] == "high"


def test_combined_embed_release_covers_b_and_d():
    res = by_wbs(cc.cross_check(ACTIVITIES, RELEASES, SUBMITTALS))
    for wbs in (1048, 2662):  # B embed, D embed
        assert res[wbs]["matched_ref"] == "526"       # the combined B-D release
        assert res[wbs]["status"] == cc.STATUS_COMPLETE


def test_anchor_bolts_match_embed_family():
    res = by_wbs(cc.cross_check(ACTIVITIES, RELEASES, SUBMITTALS))
    # Anchor-bolt activities ride with the embed/baseplate release (526, complete).
    assert res[1049]["matched_ref"] == "526"
    assert res[2663]["matched_ref"] == "526"


def test_no_record_when_nothing_matches():
    acts = [{"wbs_id": 1, "building": "Building E", "task_name": "Structural Steel", "start": date(2026, 9, 1)}]
    r = cc.cross_check(acts, RELEASES, SUBMITTALS)[0]
    assert r["status"] == cc.STATUS_NO_RECORD
    assert r["severity"] == "high"


def test_parser_and_crosscheck_end_to_end():
    """If the sample PDF is present, the parser+engine must reproduce the two headline gaps."""
    import os
    from app.brain.lookahead import parser

    here = os.path.dirname(__file__)
    pdf = os.path.join(here, "fixtures", "AMC_-_3WK_Lookahead_-_07172026.pdf")
    if not os.path.exists(pdf):
        import pytest
        pytest.skip("sample lookahead PDF not vendored into tests/lookahead/fixtures")

    acts = parser.metal_activities(pdf)
    res = {r["wbs_id"]: r for r in cc.cross_check(acts, RELEASES, SUBMITTALS)}
    steel_c = next(r for r in res.values() if r["scope"] == cc.STEEL and r["building"] == "Building C")
    steel_d = next(r for r in res.values() if r["scope"] == cc.STEEL and r["building"] == "Building D")
    assert steel_c["status"] == cc.STATUS_SLIP and steel_c["slip_days"] == 3
    assert steel_d["status"] == cc.STATUS_IN_DRAFTING
