"""
@milehigh-header
schema_version: 1
purpose: Deterministic GC-facing multi-phase lookahead schedule from a project pipeline.
  Builds drafting / fabrication / paint / shipping / installation bars for every active
  release and open DRR. Dates never invent beyond fixed rules: hard green dates win,
  stored projections next, paint is a provisional 3-business-day estimated bar, ship
  defaults to one business day before install when unset.
exports:
  build_lookahead_schedule(pipeline, weeks=3, today=None): schedule envelope for PDF/agent
  build_project_lookahead(job_number, weeks=3, today=None): pipeline + schedule convenience
  PAINT_BUSINESS_DAYS, PHASES
imports_from: [datetime, app.trello.utils, app.brain.job_log.scheduling.*, app.brain.lookahead.pipeline]
imported_by: [tests, (future) bb_chat tools]
invariants:
  - Pure given (pipeline, today, weeks). No DB writes.
  - Every phase bar carries date_source in {hard, projected, estimated, missing}.
  - Paint duration is provisional (PAINT_BUSINESS_DAYS=3) until shop calibration lands.
  - Install/ship anchors come only from stored dates (or ship = install-1bd). Never invent
    install from a job-local fab queue — that understates hours_in_front vs the full shop.
  - All active pipeline rows are included; window is metadata for the Gantt viewport.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.brain.job_log.scheduling.calculator import (
    calculate_install_complete_date,
    calculate_remaining_fab_hours,
)
from app.brain.job_log.scheduling.config import SchedulingConfig
from app.brain.lookahead.pipeline import (
    KIND_ASAP,
    KIND_HARD,
    KIND_MISSING,
    KIND_NEUTRAL,
    KIND_PROJECTED,
    get_project_pipeline,
)
from app.trello.utils import calculate_business_days_before

# Provisional until shop data analysis replaces it (user will re-gap).
PAINT_BUSINESS_DAYS = 3
SHIP_LEAD_BUSINESS_DAYS = 1
# Cap how far back an open DRR drafting bar extends on the Gantt (table keeps full dates later).
DRAFT_BAR_MAX_BUSINESS_DAYS = 15

PHASE_DRAFTING = "drafting"
PHASE_FABRICATION = "fabrication"
PHASE_PAINT = "paint"
PHASE_SHIPPING = "shipping"
PHASE_INSTALLATION = "installation"

PHASES = (
    PHASE_DRAFTING,
    PHASE_FABRICATION,
    PHASE_PAINT,
    PHASE_SHIPPING,
    PHASE_INSTALLATION,
)

# GC-facing phase labels (PDF legend / row bars).
PHASE_LABELS = {
    PHASE_DRAFTING: "Drafting",
    PHASE_FABRICATION: "Fabrication",
    PHASE_PAINT: "Paint",
    PHASE_SHIPPING: "Shipping",
    PHASE_INSTALLATION: "Installation",
}

SOURCE_HARD = "hard"
SOURCE_PROJECTED = "projected"
SOURCE_ESTIMATED = "estimated"
SOURCE_MISSING = "missing"

LEGEND = {
    SOURCE_HARD: "Committed date",
    SOURCE_PROJECTED: "Projected from production schedule",
    SOURCE_ESTIMATED: "Estimated (paint duration is provisional)",
    SOURCE_MISSING: "No date available",
}

# Stages at or past which remaining shop work (fab/paint) is done.
_POST_PAINT = frozenset({
    "paint complete", "store at mhmw", "ship planning", "ship complete",
    "install start", "install complete", "complete",
})
_POST_FAB = frozenset({
    "welded qc", "paint start",
}) | _POST_PAINT
_POST_SHIP = frozenset({
    "ship complete", "install start", "install complete", "complete",
})
_POST_INSTALL = frozenset({
    "install complete", "complete",
})


def _parse_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _stage_key(stage: Optional[str]) -> str:
    return (stage or "").strip().lower()


def _needs_fab(stage: Optional[str], is_complete: bool) -> bool:
    if is_complete:
        return False
    key = _stage_key(stage)
    if key in _POST_FAB:
        return False
    # Remaining hours map: Paint Complete+ are 0; Welded QC / Paint Start still have shop work
    # that is paint-ish, but fab remaining is already low — still show fab only pre-Welded QC.
    return key not in _POST_FAB


def _needs_paint(stage: Optional[str], is_complete: bool) -> bool:
    if is_complete:
        return False
    return _stage_key(stage) not in _POST_PAINT


def _needs_ship(stage: Optional[str], is_complete: bool) -> bool:
    if is_complete:
        return False
    return _stage_key(stage) not in _POST_SHIP


def _needs_install(stage: Optional[str], is_complete: bool) -> bool:
    if is_complete:
        return False
    return _stage_key(stage) not in _POST_INSTALL


def _gc_stage_label(row: dict) -> str:
    """Coarse GC-facing status line for a release or drafting package."""
    if row.get("kind") == "drafting":
        return "In drafting"
    if row.get("is_complete"):
        return "Complete"
    stage = _stage_key(row.get("stage"))
    if stage in _POST_INSTALL:
        return "Complete"
    if stage in ("install start",):
        return "Installing"
    if stage in ("ship complete",):
        return "Shipped"
    if stage in ("ship planning", "store at mhmw"):
        return "Ready to ship"
    if stage in ("paint start", "paint complete"):
        return "In paint"
    if stage in ("welded qc",):
        return "Fabrication complete — paint / QC"
    if stage:
        return "In fabrication"
    return "Released"


def _phase_bar(
    phase: str,
    start: Optional[date],
    end: Optional[date],
    date_source: str,
    *,
    note: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    if start is None and end is None:
        return None
    # Normalize: if only one side, treat as a point bar.
    if start is None:
        start = end
    if end is None:
        end = start
    if end < start:
        start, end = end, start
    bar = {
        "phase": phase,
        "label": PHASE_LABELS[phase],
        "start": _iso(start),
        "end": _iso(end),
        "date_source": date_source,
    }
    if note:
        bar["note"] = note
    return bar


def _paint_window(ship: date) -> tuple[date, date]:
    """Three business days ending the business day before ship."""
    paint_end = calculate_business_days_before(ship, 1)
    paint_start = calculate_business_days_before(ship, PAINT_BUSINESS_DAYS)
    return paint_start, paint_end


def _install_source(date_kind: str) -> str:
    if date_kind == KIND_HARD:
        return SOURCE_HARD
    if date_kind == KIND_ASAP:
        return SOURCE_HARD  # ASAP is an explicit commitment to go ASAP
    if date_kind == KIND_PROJECTED:
        return SOURCE_PROJECTED
    if date_kind == KIND_NEUTRAL:
        return SOURCE_HARD  # retained date, color suppressed
    return SOURCE_MISSING


def _build_release_phases(
    row: dict,
    *,
    today: date,
) -> list[dict[str, Any]]:
    """Build phase bars from **stored** dates only.

    We deliberately do not invent install/fab from a job-local fab-queue projection:
    hours_in_front requires the full shop queue (see scheduling.service), and a
    partial queue would paint optimistic GC-facing dates. Missing install stays
    missing (flagged on the row); fab/paint/ship cascade only when install or
    ship is known.
    """
    phases: list[dict[str, Any]] = []
    is_complete = bool(row.get("is_complete"))
    stage = row.get("stage")

    install_start = _parse_date(row.get("start_install"))
    install_end = _parse_date(row.get("comp_eta"))
    date_kind = row.get("date_kind") or KIND_MISSING
    install_src = _install_source(date_kind)

    if install_end is None and install_start is not None:
        install_end = calculate_install_complete_date(
            install_start, row.get("install_hrs"), row.get("num_guys")
        ) or install_start

    # --- Shipping ---
    ship = _parse_date(row.get("ship_date"))
    ship_src = SOURCE_HARD if ship else SOURCE_MISSING
    if ship is None and install_start is not None and _needs_ship(stage, is_complete):
        ship = calculate_business_days_before(install_start, SHIP_LEAD_BUSINESS_DAYS)
        ship_src = SOURCE_ESTIMATED

    # --- Paint (provisional 3-day bar, anchored to ship) ---
    paint_start = paint_end = None
    paint_src = SOURCE_ESTIMATED
    if _needs_paint(stage, is_complete) and ship is not None:
        paint_start, paint_end = _paint_window(ship)

    # --- Fabrication (back-chain only — never invent from a partial shop queue) ---
    fab_start = fab_end = None
    fab_src = SOURCE_ESTIMATED
    if _needs_fab(stage, is_complete):
        released = _parse_date(row.get("released"))

        if paint_start is not None:
            fab_end = calculate_business_days_before(paint_start, 1)
            fab_src = SOURCE_ESTIMATED
        elif ship is not None:
            fab_end = calculate_business_days_before(ship, PAINT_BUSINESS_DAYS + 1)
            fab_src = SOURCE_ESTIMATED

        if fab_end is not None:
            remaining = calculate_remaining_fab_hours(row.get("fab_hrs"), stage)
            if remaining > 0.1:
                days = max(1, int(-(-remaining // SchedulingConfig.FAB_HOURS_PER_DAY)))  # ceil
                fab_start = calculate_business_days_before(fab_end, max(days - 1, 0))
            else:
                fab_start = fab_end
            # Don't start fab bars before release day (or today) when we have a floor.
            floor = released or today
            if fab_start < floor and floor <= fab_end:
                fab_start = floor

    # Assemble in lifecycle order.
    if fab_start is not None or fab_end is not None:
        bar = _phase_bar(PHASE_FABRICATION, fab_start, fab_end, fab_src)
        if bar:
            phases.append(bar)

    if paint_start is not None:
        note = f"Provisional {PAINT_BUSINESS_DAYS}-business-day paint window"
        bar = _phase_bar(PHASE_PAINT, paint_start, paint_end, paint_src, note=note)
        if bar:
            phases.append(bar)

    if ship is not None and _needs_ship(stage, is_complete):
        bar = _phase_bar(PHASE_SHIPPING, ship, ship, ship_src)
        if bar:
            phases.append(bar)
    elif ship is not None and not is_complete and _stage_key(stage) == "ship complete":
        # Already shipped — still show the ship point if we have a date.
        bar = _phase_bar(PHASE_SHIPPING, ship, ship, ship_src or SOURCE_HARD)
        if bar:
            phases.append(bar)

    if install_start is not None and _needs_install(stage, is_complete):
        bar = _phase_bar(
            PHASE_INSTALLATION,
            install_start,
            install_end or install_start,
            install_src,
        )
        if bar:
            phases.append(bar)
    elif install_start is not None and is_complete:
        # Complete work still listed: single install marker for GC context.
        bar = _phase_bar(
            PHASE_INSTALLATION,
            install_start,
            install_end or install_start,
            install_src,
            note="Complete",
        )
        if bar:
            phases.append(bar)

    return phases


def _build_drafting_phases(row: dict, *, today: date) -> list[dict[str, Any]]:
    due = _parse_date(row.get("due_date"))
    target_install = _parse_date(row.get("start_install"))
    created = _parse_date(row.get("created_at")) or today

    phases: list[dict[str, Any]] = []
    draft_end = due or target_install
    if draft_end is None:
        # Unscheduled drafting — point bar at today so it still appears on the chart.
        bar = _phase_bar(
            PHASE_DRAFTING,
            today,
            today,
            SOURCE_MISSING,
            note="No due date set",
        )
        if bar:
            phases.append(bar)
        return phases

    # Cap multi-month open packages so the Gantt stays readable; full history is a PR2 table concern.
    span_floor = calculate_business_days_before(draft_end, DRAFT_BAR_MAX_BUSINESS_DAYS)
    draft_start = max(created, span_floor)
    if draft_start > draft_end:
        draft_start = draft_end
    # DRR due / start_install are hard commitments from DWL when set.
    src = SOURCE_HARD if (due or target_install) else SOURCE_MISSING
    bar = _phase_bar(PHASE_DRAFTING, draft_start, draft_end, src)
    if bar:
        phases.append(bar)

    # If the DRR already carries a planned install, surface it as a future install bar.
    if target_install is not None:
        bar = _phase_bar(
            PHASE_INSTALLATION,
            target_install,
            target_install,
            SOURCE_HARD,
            note="Planned install (drawings not yet released)",
        )
        if bar:
            phases.append(bar)

    return phases


def _row_flags(row: dict, phases: list[dict]) -> list[str]:
    flags = []
    if row.get("unqueued"):
        flags.append("not_in_shop_queue")
    if row.get("kind") == "release" and not row.get("is_complete"):
        if row.get("date_kind") == KIND_MISSING and not any(
            p["phase"] == PHASE_INSTALLATION for p in phases
        ):
            flags.append("missing_install_date")
        if row.get("fab_hrs") is None and any(
            p["phase"] == PHASE_FABRICATION for p in phases
        ):
            flags.append("missing_fab_hours")
    if row.get("kind") == "drafting":
        if not row.get("due_date") and not row.get("start_install"):
            flags.append("unscheduled_drafting")
    return flags


def build_lookahead_schedule(
    pipeline: dict[str, Any],
    *,
    weeks: int = 3,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Turn a ``get_project_pipeline`` envelope into a GC-facing multi-phase schedule.

    Includes **all** active releases and open drafting packages from the pipeline.
    ``window`` is the Gantt viewport (default 3 weeks from ``today``); bars outside
    the window are still present with full dates for the PDF table appendix.
    """
    today = today or date.today()
    try:
        weeks = max(1, min(int(weeks), 12))
    except (TypeError, ValueError):
        weeks = 3

    window_end = today + timedelta(days=weeks * 7)

    if not pipeline or not pipeline.get("found"):
        return {
            "found": False,
            "error": pipeline.get("error") if pipeline else "no pipeline",
            "job": pipeline.get("job") if pipeline else None,
            "project_name": pipeline.get("project_name") if pipeline else None,
            "audience": "gc",
            "window": {
                "start": _iso(today),
                "end": _iso(window_end),
                "weeks": weeks,
            },
            "generated_on": _iso(today),
            "rows": [],
            "summary": {
                "release_count": 0,
                "drafting_count": 0,
                "gc_approval_open_count": 0,
                "phase_bar_count": 0,
                "hard_install_dates": 0,
                "projected_install_dates": 0,
                "missing_install_dates": 0,
                "row_count": 0,
            },
            "legend": LEGEND,
            "phase_order": list(PHASES),
            "phase_labels": dict(PHASE_LABELS),
            "assumptions": {
                "paint_business_days": PAINT_BUSINESS_DAYS,
                "ship_lead_business_days": SHIP_LEAD_BUSINESS_DAYS,
                "paint_note": "Paint duration is a provisional estimate pending shop calibration.",
            },
            "flags": list(pipeline.get("flags") or []) if pipeline else [],
        }

    releases = list(pipeline.get("releases") or [])
    drafting = list(pipeline.get("drafting") or [])

    rows: list[dict[str, Any]] = []

    # Drafting first (upstream of fab), then releases by install date then code.
    for d in drafting:
        phases = _build_drafting_phases(d, today=today)
        rows.append({
            "kind": "drafting",
            "code": d.get("code"),
            "title": d.get("title") or d.get("code"),
            "stage_label": _gc_stage_label(d),
            "status": d.get("status"),
            "rel": d.get("rel"),
            "submittal_id": d.get("submittal_id"),
            "phases": phases,
            "flags": _row_flags(d, phases),
        })

    def _release_sort_key(r: dict):
        si = _parse_date(r.get("start_install")) or date.max
        return (r.get("is_complete") is True, si, r.get("code") or "")

    for r in sorted(releases, key=_release_sort_key):
        phases = _build_release_phases(r, today=today)
        rows.append({
            "kind": "release",
            "code": r.get("code"),
            "title": r.get("description") or r.get("code"),
            "stage_label": _gc_stage_label(r),
            "stage": r.get("stage"),
            "date_kind": r.get("date_kind"),
            "start_install": r.get("start_install"),
            "ship_date": r.get("ship_date"),
            "comp_eta": r.get("comp_eta"),
            "is_complete": r.get("is_complete"),
            "phases": phases,
            "flags": _row_flags(r, phases),
        })

    hard_n = sum(1 for r in releases if r.get("date_kind") == KIND_HARD)
    proj_n = sum(1 for r in releases if r.get("date_kind") == KIND_PROJECTED)
    miss_n = sum(
        1 for r in releases
        if r.get("date_kind") == KIND_MISSING and not r.get("is_complete")
    )
    phase_bar_count = sum(len(row["phases"]) for row in rows)

    return {
        "found": True,
        "job": pipeline.get("job"),
        "project_name": pipeline.get("project_name"),
        "audience": "gc",
        "window": {
            "start": _iso(today),
            "end": _iso(window_end),
            "weeks": weeks,
        },
        "generated_on": _iso(today),
        "rows": rows,
        "summary": {
            "release_count": len(releases),
            "drafting_count": len(drafting),
            "gc_approval_open_count": len(pipeline.get("gc_approvals") or []),
            "phase_bar_count": phase_bar_count,
            "hard_install_dates": hard_n,
            "projected_install_dates": proj_n,
            "missing_install_dates": miss_n,
            "row_count": len(rows),
        },
        "legend": LEGEND,
        "phase_order": list(PHASES),
        "phase_labels": dict(PHASE_LABELS),
        "assumptions": {
            "paint_business_days": PAINT_BUSINESS_DAYS,
            "ship_lead_business_days": SHIP_LEAD_BUSINESS_DAYS,
            "paint_note": "Paint duration is a provisional estimate pending shop calibration.",
        },
        "flags": list(pipeline.get("flags") or []),
        "gc_approvals": pipeline.get("gc_approvals") or [],
    }


def build_project_lookahead(
    job_number,
    *,
    weeks: int = 3,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Convenience: load pipeline from DB and build the GC-facing schedule."""
    pipeline = get_project_pipeline(job_number)
    return build_lookahead_schedule(pipeline, weeks=weeks, today=today)
