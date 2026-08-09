#!/usr/bin/env python3
"""Compare fab projection dates: Mon–Fri (old) vs Mon–Thu shop (N4).

Read-only. Loads FABRICATION releases from the configured DB (prefer sandbox),
recomputes the fab queue once, then projects each formula-driven release's fab
complete + install start under both calendars. Prints a summary and a sorted
detail table of shifts.

Does NOT write to the DB.

Examples:
  ENVIRONMENT=sandbox python scripts/compare_fab_calendars.py
  ENVIRONMENT=sandbox python scripts/compare_fab_calendars.py --detail 40
  ENVIRONMENT=sandbox python scripts/compare_fab_calendars.py --csv /tmp/fab_cal.csv
  ENVIRONMENT=sandbox python scripts/compare_fab_calendars.py --as-of 2026-08-11
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _delta_days(a: date | None, b: date | None) -> int | None:
    if a is None or b is None:
        return None
    return (b - a).days


def run(as_of: date, detail: int, csv_path: str | None, include_hard: bool) -> int:
    from app import create_app
    from app.brain.job_log.scheduling.calculator import (
        calculate_days_in_front,
        calculate_hours_in_front,
        calculate_remaining_fab_hours,
    )
    from app.brain.job_log.scheduling.config import SchedulingConfig
    from app.models import Releases
    from app.trello.utils import (
        CALENDAR_FIELD,
        CALENDAR_SHOP,
        add_business_days,
    )

    app = create_app()
    with app.app_context():
        env = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT") or "?"
        db_url = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        db_hint = ("…" + db_url.split("@", 1)[-1]) if "@" in db_url else db_url

        q = Releases.query.filter(
            Releases.stage_group == "FABRICATION",
            Releases.is_archived.is_(False),
        )
        # Soft-deleted out
        rows = [
            r for r in q.all()
            if r.is_active is not False
        ]

        def sort_key(j):
            fo = _safe_float(j.fab_order)
            return (
                fo if fo is not None else float("inf"),
                j.start_install or date.max,
                j.job or 0,
                str(j.release or ""),
            )

        rows.sort(key=sort_key)

        # Queue dicts for hours_in_front (same shape as scheduling service)
        job_dicts = []
        for j in rows:
            rem = calculate_remaining_fab_hours(j.fab_hrs, j.stage)
            job_dicts.append({
                "job": j.job,
                "release": j.release,
                "job_name": j.job_name,
                "stage": j.stage or "Released",
                "fab_hrs": _safe_float(j.fab_hrs) or 0.0,
                "fab_order": _safe_float(j.fab_order),
                "remaining_fab_hours": rem,
                "is_hard_date": j.start_install_formulaTF is False,
                "current_start_install": j.start_install,
                "current_comp_eta": j.comp_eta,
                "formulaTF": j.start_install_formulaTF,
            })

        total_remaining = sum(d["remaining_fab_hours"] for d in job_dicts)
        hard_n = sum(1 for d in job_dicts if d["is_hard_date"])
        soft_n = len(job_dicts) - hard_n

        comparisons = []
        for i, d in enumerate(job_dicts):
            if d["is_hard_date"] and not include_hard:
                continue

            hif = calculate_hours_in_front(d["fab_order"], job_dicts, i)
            days = calculate_days_in_front(hif)

            # Fab complete = as_of + days_in_front on each calendar
            if days == 0:
                fab_fri = as_of
                fab_thu = as_of
            else:
                fab_fri = add_business_days(as_of, days, calendar=CALENDAR_FIELD)
                fab_thu = add_business_days(as_of, days, calendar=CALENDAR_SHOP)

            # Install start = fab complete + INSTALL_BUFFER on same calendar
            # (matches pre-N4: all field; post-N4: buffer on shop)
            buf = SchedulingConfig.INSTALL_BUFFER_DAYS
            inst_fri = add_business_days(fab_fri, buf, calendar=CALENDAR_FIELD)
            inst_thu = add_business_days(fab_thu, buf, calendar=CALENDAR_SHOP)

            fab_shift = _delta_days(fab_fri, fab_thu)  # + = later under Mon–Thu
            inst_shift = _delta_days(inst_fri, inst_thu)

            comparisons.append({
                "identifier": f"{d['job']}-{d['release']}",
                "job_name": d["job_name"] or "",
                "stage": d["stage"],
                "fab_order": d["fab_order"],
                "fab_hrs": d["fab_hrs"],
                "remaining_fab_hrs": round(d["remaining_fab_hours"], 1),
                "hours_in_front": round(hif, 1),
                "days_in_front": days,
                "is_hard_date": d["is_hard_date"],
                "stored_start_install": (
                    d["current_start_install"].isoformat()
                    if d["current_start_install"] else ""
                ),
                "fab_complete_mon_fri": fab_fri.isoformat(),
                "fab_complete_mon_thu": fab_thu.isoformat(),
                "fab_shift_calendar_days": fab_shift,
                "install_start_mon_fri": inst_fri.isoformat(),
                "install_start_mon_thu": inst_thu.isoformat(),
                "install_shift_calendar_days": inst_shift,
            })

        # --- Report ---
        print("=" * 78)
        print("Fab calendar estimate: Mon–Fri vs Mon–Thu (shop)")
        print(f"  ENVIRONMENT:     {env}")
        print(f"  DB:              {db_hint}")
        print(f"  as_of:           {as_of.isoformat()} ({as_of.strftime('%A')})")
        print(f"  FAB_HOURS/day:   {SchedulingConfig.FAB_HOURS_PER_DAY}")
        print(f"  install buffer:  {SchedulingConfig.INSTALL_BUFFER_DAYS} days")
        print(f"  FABRICATION rows:{len(job_dicts)}  (hard={hard_n}, formula={soft_n})")
        print(f"  remaining fab Σ: {total_remaining:.0f} hrs  "
              f"(≈ {total_remaining / 400:.2f} shop-weeks @ 400/wk)")
        print(f"  compared:        {len(comparisons)} "
              f"({'incl. hard dates' if include_hard else 'formula-driven only'})")
        print("=" * 78)

        if not comparisons:
            print("No rows to compare.")
            return 0

        fab_shifts = [c["fab_shift_calendar_days"] for c in comparisons
                      if c["fab_shift_calendar_days"] is not None]
        inst_shifts = [c["install_shift_calendar_days"] for c in comparisons
                       if c["install_shift_calendar_days"] is not None]

        def _stats(xs: list[int], label: str) -> None:
            if not xs:
                print(f"  {label}: n/a")
                return
            print(
                f"  {label}:  mean={statistics.mean(xs):.2f}d  "
                f"median={statistics.median(xs):.1f}d  "
                f"min={min(xs)}d  max={max(xs)}d"
            )
            buckets = {}
            for x in xs:
                buckets[x] = buckets.get(x, 0) + 1
            dist = "  ".join(f"{k}d:{v}" for k, v in sorted(buckets.items()))
            print(f"    distribution: {dist}")

        print()
        print("Shift = Mon–Thu date − Mon–Fri date  (positive ⇒ later under Fridays-off)")
        _stats(fab_shifts, "Fab complete shift")
        _stats(inst_shifts, "Install start shift")

        later = sum(1 for x in fab_shifts if x > 0)
        same = sum(1 for x in fab_shifts if x == 0)
        earlier = sum(1 for x in fab_shifts if x < 0)
        print()
        print(f"  Fab complete:  {later} later · {same} same · {earlier} earlier")

        # Span of the formula queue (earliest → latest fab complete) under each calendar
        formula = [c for c in comparisons if not c["is_hard_date"]]
        if formula:
            fri_dates = sorted(date.fromisoformat(c["fab_complete_mon_fri"]) for c in formula)
            thu_dates = sorted(date.fromisoformat(c["fab_complete_mon_thu"]) for c in formula)
            print()
            print("Formula-queue fab-complete span (first → last in queue order by date):")
            print(f"  Mon–Fri:  {fri_dates[0]} → {fri_dates[-1]}  "
                  f"({(fri_dates[-1] - fri_dates[0]).days} calendar days)")
            print(f"  Mon–Thu:  {thu_dates[0]} → {thu_dates[-1]}  "
                  f"({(thu_dates[-1] - thu_dates[0]).days} calendar days)")
            print(f"  End-of-queue slip: "
                  f"{(thu_dates[-1] - fri_dates[-1]).days} calendar days later under Mon–Thu")

        # Detail: largest shifts first
        print()
        print(f"Detail (top {detail} by |fab shift|, then days_in_front):")
        print(
            f"  {'ID':12} {'dInF':>4} {'hInF':>7} {'rem':>6}  "
            f"{'fab Mon-Fri':12} {'fab Mon-Thu':12} {'Δ':>3}  "
            f"{'inst Mon-Fri':12} {'inst Mon-Thu':12} {'Δ':>3}  stage"
        )
        ranked = sorted(
            comparisons,
            key=lambda c: (
                -(abs(c["fab_shift_calendar_days"] or 0)),
                -(c["days_in_front"] or 0),
            ),
        )
        for c in ranked[:detail]:
            print(
                f"  {c['identifier']:12} {c['days_in_front']:4d} "
                f"{c['hours_in_front']:7.1f} {c['remaining_fab_hrs']:6.1f}  "
                f"{c['fab_complete_mon_fri']:12} {c['fab_complete_mon_thu']:12} "
                f"{c['fab_shift_calendar_days'] or 0:+3d}  "
                f"{c['install_start_mon_fri']:12} {c['install_start_mon_thu']:12} "
                f"{c['install_shift_calendar_days'] or 0:+3d}  "
                f"{c['stage']}"
            )
        if len(ranked) > detail:
            print(f"  … +{len(ranked) - detail} more "
                  f"(use --detail N or --csv PATH)")

        if csv_path:
            fields = list(comparisons[0].keys())
            with open(csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(comparisons)
            print()
            print(f"Wrote {len(comparisons)} rows → {csv_path}")

        print()
        print("Note: hard dates are skipped by the live cascade; include with --include-hard.")
        print("Days-in-front still uses FAB_HOURS_PER_DAY=104; only the calendar changes.")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Estimate fab date shifts Mon–Fri vs Mon–Thu on sandbox/live data (read-only)."
    )
    p.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Reference date YYYY-MM-DD (default: today).",
    )
    p.add_argument(
        "--detail",
        type=int,
        default=25,
        help="How many detail rows to print (default 25).",
    )
    p.add_argument(
        "--csv",
        type=str,
        default=None,
        dest="csv_path",
        help="Optional path to write full comparison CSV.",
    )
    p.add_argument(
        "--include-hard",
        action="store_true",
        help="Also project hard-dated rows (live cascade still skips them).",
    )
    args = p.parse_args()
    as_of = (
        date.fromisoformat(args.as_of)
        if args.as_of
        else date.today()
    )
    return run(
        as_of=as_of,
        detail=args.detail,
        csv_path=args.csv_path,
        include_hard=args.include_hard,
    )


if __name__ == "__main__":
    raise SystemExit(main())
