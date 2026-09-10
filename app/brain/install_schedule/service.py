"""
@milehigh-header
schema_version: 1
purpose: Assemble the installation schedule payload in two shapes off ONE card builder — active
  releases with a start_install in the window, either grouped by CREW (the production-meeting view,
  hard dates first, with per-crew overload and hard-date-overlap flags) or by DAY (the vertical
  calendar behind the phone view, past-due triaged out to its own bucket).
exports:
  build_next_week_schedule: (days:int=7, today:date|None=None) -> dict envelope {window, summary, crews[]}
  build_day_schedule: (days:int=14, past_days:int=14, today:date|None=None, installer:str|None=None)
    -> dict envelope {window, summary, past_due[], days[]}
imports_from: [app.models, app.brain.job_log.scheduling.calculator, app.brain.job_log.scheduling.config]
imported_by: [app/brain/install_schedule/routes.py, tests]
invariants:
  - Read-only. Deterministic given (today, DB state); no external calls.
  - "Hard date" == start_install_formulaTF is False AND not no-color (mirrors StartInstallEditor.jsx).
    An ASAP row is a hard date too — it is labelled `asap` for its colour and sorts ahead of plain hard.
  - Estimated hours come ONLY from the manual install_hrs field; never fabricated. Blank stays blank.
  - Crew grouping is by the installer string; releases with no installer fall into a single UNASSIGNED bucket.
  - Both builders share _card/_classify_date, so the crew view and the day view can never disagree
    about a release. They differ ONLY in grouping, sort and window.
  - The day view's past-due bucket holds MISSED COMMITMENTS: hard/ASAP dates only. A projected date
    that has slipped is a stale formula, not a broken promise, and would bury the real misses.
  - A multi-day install appears ONCE, on its start day, carrying span_days — never repeated across
    every day it spans.
"""
from datetime import date, timedelta

from app.models import Releases
from app.brain.job_log.scheduling.calculator import calculate_install_complete_date
from app.brain.job_log.scheduling.config import SchedulingConfig
from app.logging_config import get_logger

logger = get_logger(__name__)

UNASSIGNED = "Unassigned"

# date_kind values, in scheduling-priority order (both hard kinds are non-negotiable anchors).
KIND_ASAP = "asap"          # hard date flagged a rush — red
KIND_HARD = "hard"          # green/future hard date — non-negotiable
KIND_PROJECTED = "projected"  # formula-derived soft date
KIND_NEUTRAL = "neutral"    # no-color (release already in the complete zone)

# Sort weight: ASAP first, then plain hard, then projected, then neutral. ASAP is a hard
# date the PM marked as the one to do first, so it outranks an unflagged hard date.
_KIND_ORDER = {KIND_ASAP: 0, KIND_HARD: 1, KIND_PROJECTED: 2, KIND_NEUTRAL: 3}


def _classify_date(rel):
    """Mirror the frontend StartInstallEditor color logic to label the install date."""
    # The flag alone is not a commitment. The modal refuses to set ASAP without a hard
    # date, but the API accepts the flag on its own and legacy rows predate the rule —
    # so an ASAP row with a projected (or absent) date must classify as projected, or
    # is_hard below would feed a soft date into the crew conflict pairing.
    is_hard_date = rel.start_install_formulaTF is False and rel.start_install is not None
    if rel.start_install_asap and is_hard_date:
        return KIND_ASAP
    if rel.start_install_no_color:
        return KIND_NEUTRAL
    if is_hard_date:
        return KIND_HARD
    return KIND_PROJECTED


def _iso(d):
    return d.isoformat() if d is not None else None


def _card(rel, today):
    """Build one Trello-shaped card for a release."""
    kind = _classify_date(rel)
    # Prefer the stored comp_eta; fall back to the canonical computation so a card always
    # carries an install window when install_hrs is present.
    comp_eta = rel.comp_eta or calculate_install_complete_date(
        rel.start_install, rel.install_hrs, rel.num_guys
    )
    return {
        "release_id": rel.id,
        "code": f"{rel.job}-{rel.release}",
        "job": rel.job,
        "release": rel.release,
        "project_name": rel.job_name,
        "crew": rel.installer or UNASSIGNED,
        "unassigned": rel.installer is None,
        "num_guys": rel.num_guys,
        "start_install": _iso(rel.start_install),
        "date_kind": kind,
        # Both kinds are commitments a person made, so both count as hard for the
        # overlap and capacity math; date_kind is what distinguishes the rush.
        "is_hard": kind in (KIND_HARD, KIND_ASAP),
        "est_hours": rel.install_hrs,          # manual field; None when not entered
        "comp_eta": _iso(comp_eta),
        "stage": rel.stage,
        "notes": rel.notes,
    }


def _card_sort_key(card):
    # Hard dates first, then by date, then by code for stability.
    return (_KIND_ORDER.get(card["date_kind"], 9), card["start_install"] or "", card["code"])


def _windows_overlap(a, b):
    """True if two install windows [start, comp_eta] intersect (comp_eta defaults to start)."""
    a_start, a_end = a["start_install"], a["comp_eta"] or a["start_install"]
    b_start, b_end = b["start_install"], b["comp_eta"] or b["start_install"]
    if not (a_start and b_start):
        return False
    return a_start <= b_end and b_start <= a_end


def _crew_flags(cards):
    """Compute hard-date overlaps and weekly-overload for one crew's cards."""
    # Overlapping HARD dates only (soft dates aren't commitments).
    hard = [c for c in cards if c["is_hard"]]
    conflicts = []
    for i in range(len(hard)):
        for j in range(i + 1, len(hard)):
            if _windows_overlap(hard[i], hard[j]):
                conflicts.append([hard[i]["code"], hard[j]["code"]])

    # Overload: sum of KNOWN install hours vs the crew's weekly capacity.
    # Crew headcount = the largest num_guys seen on the crew's cards (defensive), else default.
    known = [c["est_hours"] for c in cards if c["est_hours"] is not None]
    total_known = round(sum(known), 1) if known else 0.0
    unknown_count = sum(1 for c in cards if c["est_hours"] is None)
    guy_counts = [c["num_guys"] for c in cards if c["num_guys"]]
    crew_guys = max(guy_counts) if guy_counts else SchedulingConfig.DEFAULT_NUM_GUYS
    capacity = round(crew_guys * SchedulingConfig.HOURS_PER_INSTALLER_DAY * 5, 1)  # 5-day week
    return {
        "total_known_hours": total_known,
        "unknown_hours_count": unknown_count,
        "assumed_num_guys": crew_guys,
        "weekly_capacity_hours": capacity,
        "overloaded": total_known > capacity,
        "conflicts": conflicts,
    }


def build_next_week_schedule(days=7, today=None):
    """
    Assemble the next-``days`` installation schedule grouped by crew.

    Returns an envelope:
      {window: {start, end, days}, summary: {...}, crews: [{crew, ...flags, cards: [...]}]}
    """
    today = today or date.today()
    end = today + timedelta(days=days)

    rows = (
        Releases.query
        .filter(Releases.is_active.isnot(False))
        .filter(Releases.is_archived.is_(False))
        .filter(Releases.start_install.isnot(None))
        .filter(Releases.start_install >= today)
        .filter(Releases.start_install <= end)
        .all()
    )

    cards = [_card(r, today) for r in rows]

    # Group by crew.
    by_crew = {}
    for c in cards:
        by_crew.setdefault(c["crew"], []).append(c)

    crews = []
    for crew, crew_cards in by_crew.items():
        crew_cards.sort(key=_card_sort_key)
        flags = _crew_flags(crew_cards)
        crews.append({
            "crew": crew,
            "is_unassigned": crew == UNASSIGNED,
            "card_count": len(crew_cards),
            "hard_count": sum(1 for c in crew_cards if c["is_hard"]),
            **flags,
            "cards": crew_cards,
        })

    # Named crews first (alpha), Unassigned last.
    crews.sort(key=lambda g: (g["is_unassigned"], g["crew"].lower()))

    summary = {
        "total_releases": len(cards),
        "hard_dates": sum(1 for c in cards if c["is_hard"]),
        "projected_dates": sum(1 for c in cards if c["date_kind"] == KIND_PROJECTED),
        "asap_dates": sum(1 for c in cards if c["date_kind"] == KIND_ASAP),
        "unassigned_releases": sum(1 for c in cards if c["unassigned"]),
        "crews_with_conflicts": sum(1 for g in crews if g["conflicts"]),
        "overloaded_crews": sum(1 for g in crews if g["overloaded"]),
        "releases_missing_hours": sum(1 for c in cards if c["est_hours"] is None),
    }

    logger.info(
        "install_schedule_built",
        window_start=today.isoformat(),
        window_end=end.isoformat(),
        total_releases=summary["total_releases"],
        hard_dates=summary["hard_dates"],
        unassigned=summary["unassigned_releases"],
    )

    return {
        "window": {"start": today.isoformat(), "end": end.isoformat(), "days": days},
        "summary": summary,
        "crews": crews,
    }


# --- Day-row schedule (mobile vertical calendar) ------------------------------
#
# Same cards as the crew view, pivoted: DAYS are the rows and the crew becomes a
# chip on the card. The desktop timeline needs 392px of frozen lane chrome before
# it can draw a column, which is wider than a phone; days-as-rows needs none of it.


def _span_days(card):
    """Calendar days a card's install window covers, inclusive.

    1 when comp_eta is missing or lands on the start day. A multi-day install is
    rendered ONCE on its start day carrying this count — never repeated on each
    day it spans, which would make one 3-day job read as three jobs.
    """
    start, end = card["start_install"], card["comp_eta"]
    if not start or not end or end <= start:
        return 1
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def _day_row_sort_key(card):
    """Order within ONE day row: rush first, then code.

    Deliberately not `_card_sort_key`. That one sorts by date because a crew column
    mixes dates; here the row IS the date, so the date carries no information and
    sorting by it would just scramble the rush ordering.
    """
    return (_KIND_ORDER.get(card["date_kind"], 9), card["code"])


def _hours(cards):
    known = [c["est_hours"] for c in cards if c["est_hours"] is not None]
    return round(sum(known), 1) if known else 0.0


def build_day_schedule(days=14, past_days=14, today=None, installer=None):
    """
    Assemble the installation schedule as DAY ROWS for the vertical calendar.

    Window runs ``past_days`` back to ``days`` forward. Everything before today is
    triaged into ``past_due`` rather than given a row of its own, so the list opens
    on what is next without hiding what was missed.

    Returns an envelope:
      {window: {...}, summary: {...}, past_due: [card], days: [{date, cards, ...}]}
    """
    today = today or date.today()
    window_start = today - timedelta(days=past_days)
    window_end = today + timedelta(days=days)
    today_iso = today.isoformat()

    q = (
        Releases.query
        .filter(Releases.is_active.isnot(False))
        .filter(Releases.is_archived.is_(False))
        .filter(Releases.start_install.isnot(None))
        .filter(Releases.start_install >= window_start)
        .filter(Releases.start_install <= window_end)
    )
    if installer:
        q = q.filter(Releases.installer == installer)

    cards = []
    for rel in q.all():
        card = _card(rel, today)
        card["span_days"] = _span_days(card)
        cards.append(card)

    # Past due == a MISSED COMMITMENT, so hard dates only. A projected date that has
    # slipped by is a stale formula, not a promise anyone broke; including those would
    # bury the real misses under every drafting row the calculator ever dated. Neutral
    # (already installed) rows are excluded for free — `is_hard` never covers them.
    past_due = sorted(
        (c for c in cards if c["start_install"] < today_iso and c["is_hard"]),
        key=lambda c: (c["start_install"], c["code"]),   # longest-overdue leads
    )

    by_day = {}
    for c in cards:
        if c["start_install"] >= today_iso:
            by_day.setdefault(c["start_install"], []).append(c)

    # Emit EVERY day in the forward window, empty ones included, so the frontend
    # renders the shape of the week rather than reconstructing the gaps itself.
    day_rows = []
    for offset in range(days + 1):
        d = today + timedelta(days=offset)
        day_cards = sorted(by_day.get(d.isoformat(), []), key=_day_row_sort_key)
        day_rows.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "is_today": d == today,
            "is_weekend": d.weekday() >= 5,
            "card_count": len(day_cards),
            "known_hours": _hours(day_cards),
            "unknown_hours_count": sum(1 for c in day_cards if c["est_hours"] is None),
            "cards": day_cards,
        })

    scheduled = sum(r["card_count"] for r in day_rows)
    summary = {
        "total_releases": len(cards),
        "scheduled": scheduled,
        "past_due": len(past_due),
        "hard_dates": sum(1 for c in cards if c["is_hard"]),
        "asap_dates": sum(1 for c in cards if c["date_kind"] == KIND_ASAP),
        "unassigned_releases": sum(1 for c in cards if c["unassigned"]),
        "releases_missing_hours": sum(1 for c in cards if c["est_hours"] is None),
        # Drives the crew filter chips; sorted so the control doesn't reshuffle per poll.
        "crews": sorted({c["crew"] for c in cards}),
    }

    logger.info(
        "day_schedule_built",
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        installer=installer,
        scheduled=scheduled,
        past_due=len(past_due),
    )

    return {
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "today": today_iso,
            "days": days,
            "past_days": past_days,
            "installer": installer,
        },
        "summary": summary,
        "past_due": past_due,
        "days": day_rows,
    }
