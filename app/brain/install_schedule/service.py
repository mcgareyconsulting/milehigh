"""
@milehigh-header
schema_version: 1
purpose: Assemble the next-week installation schedule payload — active releases with a start_install in the coming N days, grouped by crew, hard dates first, with per-crew overload and hard-date-overlap flags.
exports:
  build_next_week_schedule: (days:int=7, today:date|None=None) -> dict envelope {window, summary, crews[]}
imports_from: [app.models, app.brain.job_log.scheduling.calculator, app.brain.job_log.scheduling.config]
imported_by: [app/brain/install_schedule/routes.py, tests]
invariants:
  - Read-only. Deterministic given (today, DB state); no external calls.
  - "Hard date" == start_install_formulaTF is False AND not ASAP AND not no-color (mirrors StartInstallEditor.jsx).
  - Estimated hours come ONLY from the manual install_hrs field; never fabricated. Blank stays blank.
  - Crew grouping is by the installer string; releases with no installer fall into a single UNASSIGNED bucket.
"""
from datetime import date, timedelta

from app.models import Releases
from app.brain.job_log.scheduling.calculator import calculate_install_complete_date
from app.brain.job_log.scheduling.config import SchedulingConfig
from app.logging_config import get_logger

logger = get_logger(__name__)

UNASSIGNED = "Unassigned"

# date_kind values, in scheduling-priority order (hard is the non-negotiable anchor).
KIND_HARD = "hard"          # green/future hard date — non-negotiable
KIND_ASAP = "asap"          # red ASAP flag
KIND_PROJECTED = "projected"  # formula-derived soft date
KIND_NEUTRAL = "neutral"    # no-color (release already in the complete zone)

# Sort weight: hard first, then asap, then projected, then neutral.
_KIND_ORDER = {KIND_HARD: 0, KIND_ASAP: 1, KIND_PROJECTED: 2, KIND_NEUTRAL: 3}


def _classify_date(rel):
    """Mirror the frontend StartInstallEditor color logic to label the install date."""
    if rel.start_install_asap:
        return KIND_ASAP
    if rel.start_install_no_color:
        return KIND_NEUTRAL
    if rel.start_install_formulaTF is False and rel.start_install is not None:
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
        "is_hard": kind == KIND_HARD,
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
