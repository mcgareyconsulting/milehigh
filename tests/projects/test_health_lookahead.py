"""Health-score wiring for the GC lookahead cross-check.

Verifies that GC-benchmark deductions fire, that they supersede the internal stale_drr
signal (no double-count), and that the Alta Metro scenario lands at the expected score.
"""
from datetime import date, timedelta

from app.brain.projects import service

TODAY = date.today()
FUTURE = TODAY + timedelta(days=30)


def rel(**kw):
    from types import SimpleNamespace
    base = dict(release="X", job_name="J", description="d", stage="Released", stage_group="FAB",
                fab_hrs=10, install_hrs=0, start_install=FUTURE, ship_date=None, fab_order=1.0,
                pm=None, installer=None, job_comp=None, invoiced=None, viewer_url=None)
    base.update(kw)
    return SimpleNamespace(**base)


def rows(models):
    return [service._release_row(r) for r in models]


def lookahead(activities):
    return {"source": "mock", "gc": "GC", "issued": "2026-07-17", "activities": activities}


def test_no_lookahead_leaves_score_on_internal_signals():
    hs = service._health_score(rows([rel(start_install=FUTURE)]), [], [], None)
    assert hs["score"] == 100 and hs["band"] == "green"


def test_in_drafting_gap_deducts_20():
    la = lookahead([{"wbs_id": 2668, "building": "Building D", "scope": "steel",
                     "status": "in_drafting", "severity": "high", "gc_need": "2026-08-04",
                     "our_date": None, "slip_days": None}])
    hs = service._health_score(rows([rel(start_install=FUTURE)]), [], [], la)
    assert hs["score"] == 80
    assert hs["band"] == "amber"
    assert any("in drafting" in d["reason"] for d in hs["deductions"])


def test_small_slip_deducts_6_large_slip_deducts_12():
    small = lookahead([{"wbs_id": 1, "building": "Building C", "scope": "steel", "status": "slip",
                        "severity": "medium", "gc_need": "2026-07-21", "our_date": "2026-07-24", "slip_days": 3}])
    big = lookahead([{"wbs_id": 1, "building": "Building C", "scope": "steel", "status": "slip",
                      "severity": "high", "gc_need": "2026-07-21", "our_date": "2026-08-10", "slip_days": 20}])
    assert service._health_score(rows([rel(start_install=FUTURE)]), [], [], small)["score"] == 94
    assert service._health_score(rows([rel(start_install=FUTURE)]), [], [], big)["score"] == 88


def test_lookahead_supersedes_internal_stale_drr():
    from types import SimpleNamespace
    stale = SimpleNamespace(type="Drafting Release Review", status="Open",
                            start_install=None, due_date=None)
    # Without lookahead: stale_drr costs 6.
    assert service._health_score(rows([rel(start_install=FUTURE)]), [stale], [], None)["score"] == 94
    # With lookahead present, the generic stale_drr is suppressed (only the GC deduction remains).
    la = lookahead([{"wbs_id": 2668, "building": "Building D", "scope": "steel", "status": "in_drafting",
                     "severity": "high", "gc_need": "2026-08-04", "our_date": None, "slip_days": None}])
    hs = service._health_score(rows([rel(start_install=FUTURE)]), [stale], [], la)
    assert hs["score"] == 80  # 100 - 20 only, not - 20 - 6
    assert not any(d["key"] == "stale_drr" for d in hs["deductions"])


def test_alta_metro_scenario_lands_at_74_amber():
    # Bldg D steel in drafting (-20) + Bldg C steel 3-day slip (-6) = 74.
    la = lookahead([
        {"wbs_id": 2668, "building": "Building D", "scope": "steel", "status": "in_drafting",
         "severity": "high", "gc_need": "2026-08-04", "our_date": None, "slip_days": None},
        {"wbs_id": 1888, "building": "Building C", "scope": "steel", "status": "slip",
         "severity": "medium", "gc_need": "2026-07-21", "our_date": "2026-07-24", "slip_days": 3},
        {"wbs_id": 1048, "building": "Building B", "scope": "embed", "status": "complete",
         "severity": "ok", "gc_need": "2026-08-03", "our_date": None, "slip_days": None},
    ])
    hs = service._health_score(rows([rel(start_install=FUTURE)]), [], [], la)
    assert hs["score"] == 74
    assert hs["band"] == "amber"
    assert len(hs["deductions"]) == 2  # complete activity contributes nothing
