"""Unit tests for the Projects health-score engine (app/brain/projects/service.py).

These exercise the pure scoring/derivation helpers with lightweight fakes — no Flask
app context or DB. They pin the rubric weights, the band cutoffs, the neutral states
(complete / on-hold / no-data), and the two new gap signals (unsequenced fab, stale DRR).
"""
from datetime import date, timedelta
from types import SimpleNamespace

from app.api.helpers import DEFAULT_FAB_ORDER
from app.brain.projects import service

TODAY = date.today()
PAST = TODAY - timedelta(days=5)
SOON = TODAY + timedelta(days=3)
FAR = TODAY + timedelta(days=90)


def rel(**kw):
    """A release model stand-in for _release_row (only the read attributes)."""
    base = dict(
        release="X", job_name="J", description="d", stage="Released", stage_group="FAB",
        fab_hrs=10, install_hrs=0, start_install=None, ship_date=None,
        fab_order=1.0, pm=None, installer=None, job_comp=None, invoiced=None,
        viewer_url=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def sub(**kw):
    base = dict(type="Drafting Release Review", status="Open", start_install=None,
                due_date=None, rel=None, title="t", ball_in_court=None,
                submittal_manager=None, order_number=1.0)
    base.update(kw)
    return SimpleNamespace(**base)


# ---- signal derivation on a single release --------------------------------

def test_unsequenced_flag_set_when_placeholder_and_scheduled():
    row = service._release_row(rel(fab_order=DEFAULT_FAB_ORDER, start_install=SOON))
    assert row["unsequenced"] is True
    assert row["at_risk"] is False


def test_unsequenced_ignored_without_install_date():
    # Placeholder fab order but nothing scheduling it → not a queue gap yet.
    row = service._release_row(rel(fab_order=DEFAULT_FAB_ORDER, start_install=None))
    assert row["unsequenced"] is False


def test_unsequenced_ignored_when_complete():
    row = service._release_row(
        rel(fab_order=DEFAULT_FAB_ORDER, start_install=SOON, stage="Install Complete")
    )
    assert row["unsequenced"] is False
    assert row["pct"] == 100


def test_at_risk_when_install_past_and_not_complete():
    row = service._release_row(rel(start_install=PAST, stage="Fitup Start"))
    assert row["at_risk"] is True


def test_at_risk_false_when_complete_even_if_install_past():
    row = service._release_row(rel(start_install=PAST, job_comp="X"))
    assert row["at_risk"] is False


# ---- stale DRR ------------------------------------------------------------

def test_stale_drr_true_when_open_and_no_dates():
    assert service._is_stale_drr(sub()) is True


def test_stale_drr_false_when_scheduled():
    assert service._is_stale_drr(sub(due_date=FAR)) is False
    assert service._is_stale_drr(sub(start_install=FAR)) is False


def test_stale_drr_false_when_closed_or_not_drr():
    assert service._is_stale_drr(sub(status="Closed")) is False
    assert service._is_stale_drr(sub(type="Submittal for GC  Approval")) is False


# ---- composite score ------------------------------------------------------

def score_of(release_models, submittal_models):
    releases = [service._release_row(r) for r in release_models]
    submittals = [service._submittal_row(s) for s in submittal_models]
    return service._health_score(releases, submittal_models, submittals)


def test_perfect_project_scores_100_green():
    hs = score_of([rel(start_install=FAR, stage="Fitup Start")], [])
    assert hs["score"] == 100
    assert hs["band"] == "green"
    assert hs["deductions"] == []


def test_single_at_risk_release_deducts_10_still_green():
    # One at-risk release costs 10 → 90, which stays green (cutoff is 85).
    hs = score_of([rel(start_install=PAST, stage="Fitup Start")], [])
    assert hs["score"] == 90
    assert hs["band"] == "green"
    assert hs["deductions"][0]["key"] == "install_at_risk"
    assert hs["deductions"][0]["points"] == -10


def test_crosses_into_amber_below_85():
    # Two at-risk releases → 80, into amber.
    releases = [rel(release=str(i), start_install=PAST, stage="Fitup Start") for i in range(2)]
    hs = score_of(releases, [])
    assert hs["score"] == 80
    assert hs["band"] == "amber"


def test_deductions_stack_and_cap():
    # 4 at-risk releases → 4*10 capped at 30.
    releases = [rel(release=str(i), start_install=PAST, stage="Fitup Start") for i in range(4)]
    hs = score_of(releases, [])
    ded = next(d for d in hs["deductions"] if d["key"] == "install_at_risk")
    assert ded["points"] == -30  # capped, not -40
    assert ded["count"] == 4


def test_red_band_below_65():
    releases = [
        rel(release="a", start_install=PAST, stage="Fitup Start"),        # -10
        rel(release="b", fab_order=DEFAULT_FAB_ORDER, start_install=SOON),  # -10 unsequenced
    ]
    subs = [sub(status="Open", due_date=PAST), sub(status="Open"), sub(status="Open")]
    # overdue: 1*8; stale drr: sub #2 and #3 (no dates) => 2*6=12
    hs = score_of(releases, subs)
    # 100 -10 -10 -8 -12 = 60 -> red
    assert hs["score"] == 60
    assert hs["band"] == "red"


def test_deductions_sorted_biggest_first():
    releases = [rel(start_install=PAST, stage="Fitup Start")]
    subs = [sub(status="Open")]  # stale drr -6
    hs = score_of(releases, subs)
    pts = [d["points"] for d in hs["deductions"]]
    assert pts == sorted(pts)  # most negative first


# ---- neutral lifecycle states ---------------------------------------------

def test_complete_project_is_neutral_no_score():
    hs = score_of([rel(stage="Install Complete")], [])
    assert hs["state"] == "complete"
    assert hs["score"] is None
    assert hs["band"] == "neutral"


def test_all_blocked_project_is_on_hold_neutral():
    hs = score_of([rel(stage="Hold", start_install=PAST)], [])
    assert hs["state"] == "on_hold"
    assert hs["score"] is None


def test_no_releases_is_no_data():
    hs = score_of([], [])
    assert hs["state"] == "no_data"
    assert hs["score"] is None


# ---- upcoming feed --------------------------------------------------------

def test_upcoming_includes_install_and_ship_within_window():
    releases = [service._release_row(rel(start_install=SOON, ship_date=SOON, stage="Fitup Start"))]
    up = service._upcoming_events(releases, within_days=21)
    kinds = {e["kind"] for e in up}
    assert kinds == {"install", "ship"}


def test_upcoming_excludes_far_and_complete():
    releases = [
        service._release_row(rel(release="far", start_install=FAR, stage="Fitup Start")),
        service._release_row(rel(release="done", start_install=SOON, stage="Install Complete")),
    ]
    assert service._upcoming_events(releases) == []
