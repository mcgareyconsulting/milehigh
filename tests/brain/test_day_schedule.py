"""Day-row schedule — the vertical calendar behind the phone view.

The desktop timeline freezes 392px of lane chrome (GanttChart STAGING_PX +
SIDEBAR_PX) before it can draw a single date column, which is wider than a phone.
This builder pivots the SAME cards the crew view serves: days become the rows and
the crew becomes a chip on the card, so no horizontal chrome is needed at all.

The three things worth pinning, because each one is a judgement call that a
future refactor could quietly reverse:
  * PAST DUE IS HARD DATES ONLY. A projected date that has slipped is a stale
    formula, not a promise anyone broke. Let projected rows in and the bucket
    fills with every drafting row the calculator ever dated, burying the real
    misses — which is the entire reason the bucket exists.
  * A MULTI-DAY INSTALL APPEARS ONCE, on its start day, carrying span_days.
    Repeating it across the days it spans makes one 3-day job read as three jobs.
  * WITHIN A DAY ROW the date carries no information (it IS the row), so cards
    sort by rush then code — not by date the way a crew column does.
"""
from datetime import date, timedelta

import pytest

from app.brain.install_schedule.service import build_day_schedule
from tests.conftest import make_release as _make_release


TODAY = date(2026, 9, 10)


def _iso(d):
    return d.isoformat()


def _hard(job, release, day, **kw):
    """A release with a hard (committed) start_install on `day`."""
    kw.setdefault("stage", "Ship Planning")
    kw.setdefault("installer", "Octavio")
    return _make_release(
        job, release,
        start_install=day,
        start_install_formulaTF=False,
        **kw,
    )


def _projected(job, release, day, **kw):
    """A release whose start_install came from the scheduling formula."""
    kw.setdefault("stage", "Cut Start")
    kw.setdefault("installer", "Octavio")
    return _make_release(
        job, release,
        start_install=day,
        start_install_formulaTF=True,
        **kw,
    )


def _codes(cards):
    return [c["code"] for c in cards]


def _day(envelope, day):
    """The day row for `day`, or None when it falls outside the forward window."""
    return next((r for r in envelope["days"] if r["date"] == _iso(day)), None)


# --- past due ----------------------------------------------------------------

def test_missed_hard_date_lands_in_past_due_not_a_day_row(app):
    _hard(560, "941", TODAY - timedelta(days=3))

    env = build_day_schedule(today=TODAY)

    assert _codes(env["past_due"]) == ["560-941"]
    # ...and it is NOT also duplicated into the forward rows.
    assert all(r["card_count"] == 0 for r in env["days"])


def test_projected_date_in_the_past_is_not_past_due(app):
    """The bucket is missed COMMITMENTS. A slipped formula date is neither a
    commitment nor actionable, and there are far more of them than real misses."""
    _projected(560, "942", TODAY - timedelta(days=3))

    env = build_day_schedule(today=TODAY)

    assert env["past_due"] == []
    assert env["summary"]["past_due"] == 0


def test_past_due_leads_with_the_longest_overdue(app):
    _hard(560, "recent", TODAY - timedelta(days=1))
    _hard(560, "oldest", TODAY - timedelta(days=9))
    _hard(560, "middle", TODAY - timedelta(days=4))

    env = build_day_schedule(today=TODAY)

    assert _codes(env["past_due"]) == ["560-oldest", "560-middle", "560-recent"]


def test_past_days_zero_drops_the_bucket_entirely(app):
    """The crew view's window starts at today; past_days=0 reproduces it exactly."""
    _hard(560, "941", TODAY - timedelta(days=3))

    env = build_day_schedule(today=TODAY, past_days=0)

    assert env["past_due"] == []


def test_an_installed_release_is_not_past_due(app):
    """no_color marks a release that reached the complete zone. It classifies as
    `neutral`, which is not hard, so it never reads as a miss."""
    _hard(560, "941", TODAY - timedelta(days=3), start_install_no_color=True)

    env = build_day_schedule(today=TODAY)

    assert env["past_due"] == []


# --- day rows ----------------------------------------------------------------

def test_every_day_in_the_window_gets_a_row_including_empty_ones(app):
    env = build_day_schedule(today=TODAY, days=14)

    assert len(env["days"]) == 15            # today through today+14, inclusive
    assert env["days"][0]["date"] == _iso(TODAY)
    assert env["days"][0]["is_today"] is True
    assert env["days"][-1]["date"] == _iso(TODAY + timedelta(days=14))


def test_card_lands_on_its_start_day(app):
    _hard(560, "941", TODAY + timedelta(days=2))

    env = build_day_schedule(today=TODAY)

    assert _codes(_day(env, TODAY + timedelta(days=2))["cards"]) == ["560-941"]
    assert _day(env, TODAY + timedelta(days=1))["card_count"] == 0


def test_weekends_are_flagged_so_the_view_can_thin_them(app):
    env = build_day_schedule(today=date(2026, 9, 7), days=7)   # a Monday
    weekend = [r["weekday"] for r in env["days"] if r["is_weekend"]]

    assert weekend == ["Sat", "Sun"]


def test_within_a_day_asap_leads_then_code(app):
    """The row IS the date, so date-sorting inside it would only scramble the rush."""
    _hard(560, "b", TODAY, start_install_asap=False)
    _hard(560, "a", TODAY, start_install_asap=False)
    _hard(560, "z", TODAY, start_install_asap=True)

    env = build_day_schedule(today=TODAY)

    assert _codes(_day(env, TODAY)["cards"]) == ["560-z", "560-a", "560-b"]


# --- multi-day spans ---------------------------------------------------------

def test_multi_day_install_appears_once_carrying_its_span(app):
    _hard(560, "941", TODAY, comp_eta=TODAY + timedelta(days=2))

    env = build_day_schedule(today=TODAY)

    assert _codes(_day(env, TODAY)["cards"]) == ["560-941"]
    assert _day(env, TODAY)["cards"][0]["span_days"] == 3
    # Not smeared across the days it covers.
    assert _day(env, TODAY + timedelta(days=1))["card_count"] == 0
    assert _day(env, TODAY + timedelta(days=2))["card_count"] == 0


def test_same_day_install_spans_one_day(app):
    _hard(560, "941", TODAY, comp_eta=TODAY)

    env = build_day_schedule(today=TODAY)

    assert _day(env, TODAY)["cards"][0]["span_days"] == 1


def test_comp_eta_before_start_never_yields_a_negative_span(app):
    """Stale comp_eta rows exist; the timeline clamps them and so must this."""
    _hard(560, "941", TODAY, comp_eta=TODAY - timedelta(days=4))

    env = build_day_schedule(today=TODAY)

    assert _day(env, TODAY)["cards"][0]["span_days"] == 1


# --- hours -------------------------------------------------------------------

def test_day_hours_sum_known_only_and_count_the_blanks(app):
    """install_hrs is a manual field. Blank stays blank rather than being guessed."""
    _hard(560, "a", TODAY, install_hrs=8.0)
    _hard(560, "b", TODAY, install_hrs=4.5)
    _hard(560, "c", TODAY)                    # no hours entered

    row = _day(build_day_schedule(today=TODAY), TODAY)

    assert row["known_hours"] == 12.5
    assert row["unknown_hours_count"] == 1


# --- installer scoping -------------------------------------------------------

def test_installer_filter_scopes_to_one_crew(app):
    _hard(560, "a", TODAY, installer="Octavio")
    _hard(560, "b", TODAY, installer="Saul 2")

    env = build_day_schedule(today=TODAY, installer="Saul 2")

    assert _codes(_day(env, TODAY)["cards"]) == ["560-b"]
    assert env["window"]["installer"] == "Saul 2"


def test_crew_list_is_sorted_so_filter_chips_do_not_reshuffle(app):
    _hard(560, "a", TODAY, installer="Saul 2")
    _hard(560, "b", TODAY, installer="Octavio")
    _hard(560, "c", TODAY, installer=None)

    env = build_day_schedule(today=TODAY)

    assert env["summary"]["crews"] == ["Octavio", "Saul 2", "Unassigned"]


# --- window ------------------------------------------------------------------

def test_releases_outside_the_window_are_excluded(app):
    _hard(560, "early", TODAY - timedelta(days=40))
    _hard(560, "late", TODAY + timedelta(days=40))
    _hard(560, "inside", TODAY + timedelta(days=1))

    env = build_day_schedule(today=TODAY, days=14, past_days=14)

    assert env["summary"]["total_releases"] == 1
    assert _codes(_day(env, TODAY + timedelta(days=1))["cards"]) == ["560-inside"]


def test_archived_and_soft_deleted_rows_never_appear(app):
    _hard(560, "archived", TODAY, is_archived=True)
    _hard(560, "deleted", TODAY, is_active=False)
    _hard(560, "live", TODAY)

    env = build_day_schedule(today=TODAY)

    assert _codes(_day(env, TODAY)["cards"]) == ["560-live"]


def test_summary_counts_past_due_and_scheduled_separately(app):
    _hard(560, "missed", TODAY - timedelta(days=2))
    _hard(560, "today", TODAY)
    _hard(560, "soon", TODAY + timedelta(days=3))

    s = build_day_schedule(today=TODAY)["summary"]

    assert s["past_due"] == 1
    assert s["scheduled"] == 2
    assert s["total_releases"] == 3
