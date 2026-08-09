#!/usr/bin/env python3
"""Eyeball EOS scorecard metrics against the DB Carmen will query.

Read-only. Prints a human summary of every ready/near-ready metric (or a
subset) for one Mon–Sun week so you can compare to the leadership app export.

Uses whatever DB the app config points at (ENVIRONMENT / .env) — same as
`python run.py`. Prefer sandbox when poking around.

Examples:
  # Current week, all owners
  python scripts/eyeball_eos_metrics.py

  # Last week, full dump
  python scripts/eyeball_eos_metrics.py --weeks-back 1

  # Specific scorecard week (any day in Mon–Sun)
  python scripts/eyeball_eos_metrics.py --week-of 2026-08-05

  # One owner / one metric
  python scripts/eyeball_eos_metrics.py --owner david --weeks-back 1
  python scripts/eyeball_eos_metrics.py --metric yellow_dates

  # Raw JSON (pipe to jq)
  python scripts/eyeball_eos_metrics.py --weeks-back 1 --json

  # Show more detail rows
  python scripts/eyeball_eos_metrics.py --weeks-back 1 --detail 25
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root on path when run as `python scripts/eyeball_eos_metrics.py`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _headline(result: dict) -> str:
    """One-line headline for a metric result."""
    mid = result.get("metric")
    if mid == "hours_released_to_production":
        return (
            f"{result.get('release_count', 0)} releases · "
            f"{result.get('total_fab_hrs', 0)} fab hrs released"
        )
    if mid == "yellow_dates":
        n = result.get("yellow_count", 0)
        as_of = result.get("as_of", "?")
        flag = "✓ goal met" if result.get("goal_met") else "✗ over goal"
        return f"{n} yellow hard dates (as of {as_of}) · {flag}"
    if mid == "fabrication_hours":
        return (
            f"{result.get('total_fab_hrs_completed', 0)} fab hrs completed · "
            f"{result.get('transitions_credited', 0)} transitions credited"
        )
    if mid == "qc_completed":
        pct = result.get("pct")
        pct_s = f"{pct}%" if pct is not None else "n/a"
        return (
            f"{result.get('numerator', 0)}/{result.get('denominator', 0)} "
            f"hit Welded QC · {pct_s}"
        )
    if mid == "fab_backlog":
        return (
            f"{result.get('remaining_fab_hrs', 0)} remaining fab hrs · "
            f"{result.get('releases_with_remaining_fab', 0)} releases in fab"
        )
    if mid == "tm_hours":
        return (
            f"{result.get('total_tm_hours', 0)} T&M hrs "
            f"(reg {result.get('hours_reg', 0)} / ot {result.get('hours_ot', 0)} / "
            f"dt {result.get('hours_dt', 0)}) · "
            f"{result.get('ticket_count', 0)} tickets"
        )
    if mid == "target_dates_met":
        pct = result.get("pct")
        pct_s = f"{pct}%" if pct is not None else "n/a"
        return (
            f"{result.get('numerator', 0)}/{result.get('denominator', 0)} "
            f"hard dates complete · {pct_s}"
        )
    if mid == "releases_met_or_allocated":
        pct = result.get("pct")
        pct_s = f"{pct}%" if pct is not None else "n/a"
        return (
            f"{result.get('numerator', 0)}/{result.get('denominator', 0)} "
            f"met or allocated · {pct_s} "
            f"(met={result.get('met_count')}, allocated={result.get('allocated_count')})"
        )
    if result.get("error"):
        return f"ERROR: {result['error']}"
    return "(no headline)"


def _detail_lines(result: dict, limit: int) -> list[str]:
    if limit <= 0:
        return []
    lines = []
    mid = result.get("metric")

    if mid == "hours_released_to_production":
        for r in (result.get("releases") or [])[:limit]:
            lines.append(
                f"    {r.get('identifier'):12}  {r.get('fab_hrs', 0):7.1f} hrs  "
                f"released {r.get('released')}  {r.get('project_name') or ''}"
            )
        trunc = result.get("releases_truncated") or 0
        if trunc:
            lines.append(f"    … +{trunc} more")

    elif mid == "yellow_dates":
        for r in (result.get("releases") or [])[:limit]:
            lines.append(
                f"    {r.get('identifier'):12}  start {r.get('start_install')}  "
                f"overdue {r.get('days_overdue')}d  pm={r.get('pm') or '—'}  "
                f"{r.get('stage') or ''}"
            )
        trunc = result.get("releases_truncated") or 0
        if trunc:
            lines.append(f"    … +{trunc} more")

    elif mid == "fabrication_hours":
        for t in (result.get("transitions") or [])[:limit]:
            lines.append(
                f"    {t.get('identifier'):12}  {t.get('from_stage')} → {t.get('to_stage')}  "
                f"+{t.get('completed_hrs')} hrs  (fab_hrs={t.get('fab_hrs_on_release')})"
            )
        trunc = result.get("transitions_truncated") or 0
        if trunc:
            lines.append(f"    … +{trunc} more")

    elif mid == "qc_completed":
        for r in (result.get("releases") or [])[:limit]:
            hit = "QC" if r.get("hit_welded_qc") else "  "
            lines.append(
                f"    {r.get('identifier'):12}  [{hit}]  "
                f"stages={r.get('post_fab_stages_this_week')}  "
                f"now={r.get('current_stage')}"
            )

    elif mid == "tm_hours":
        for t in (result.get("tickets") or [])[:limit]:
            lines.append(
                f"    ticket #{t.get('ticket_id')}  job={t.get('job')}  "
                f"{t.get('date_of_work')}  {t.get('hours_total')} hrs  "
                f"({t.get('status')})"
            )

    elif mid in ("target_dates_met", "releases_met_or_allocated"):
        for r in (result.get("releases") or [])[:limit]:
            flags = []
            if r.get("met"):
                flags.append("met")
            if r.get("allocated"):
                flags.append("allocated")
            if r.get("success") is False:
                flags.append("MISS")
            if r.get("met") is False and "met" not in flags and mid == "target_dates_met":
                flags.append("MISS")
            lines.append(
                f"    {r.get('identifier'):12}  install {r.get('start_install')}  "
                f"installer={r.get('installer') or '—'}  "
                f"{r.get('stage') or ''}  [{', '.join(flags) or '—'}]"
            )
        trunc = result.get("releases_truncated") or 0
        if trunc:
            lines.append(f"    … +{trunc} more")

    return lines


def _print_metric(result: dict, detail: int) -> None:
    if result.get("error"):
        print(f"  ERROR: {result['error']}")
        return
    owner = result.get("scorecard_owner", "?")
    label = result.get("metric_label", result.get("metric"))
    goal = result.get("goal", "")
    week = result.get("week") or {}
    print(f"  {label}")
    print(f"    owner: {owner}   goal: {goal}")
    if week:
        print(f"    week:  {week.get('label')}  ({week.get('start')} → {week.get('end')})")
    print(f"    → {_headline(result)}")
    rules = result.get("rules") or {}
    if rules.get("definition"):
        print(f"    def:   {rules['definition']}")
    elif rules.get("formula"):
        print(f"    def:   {rules['formula']}")
    for line in _detail_lines(result, detail):
        print(line)
    print()


def run(
    weeks_back: int = 0,
    week_of: str | None = None,
    owner: str | None = None,
    metric: str | None = None,
    as_json: bool = False,
    detail: int = 10,
) -> int:
    import os

    from app import create_app
    from app.brain.carmen_chat import eos_metrics

    app = create_app()
    with app.app_context():
        env = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT") or "?"
        # Mask credentials if a URL is present
        db_url = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        db_hint = db_url
        if "@" in db_url:
            db_hint = "…" + db_url.split("@", 1)[-1]

        results: list[dict] = []

        if metric:
            results.append(
                eos_metrics.get_eos_metric(
                    metric, weeks_back=weeks_back, week_of=week_of
                )
            )
        elif owner:
            key = eos_metrics.resolve_owner_key(owner)
            if key is None:
                print(
                    f"Unknown owner {owner!r}. Use: "
                    + ", ".join(eos_metrics.OWNERS.keys()),
                    file=sys.stderr,
                )
                return 2
            bundle = eos_metrics.get_eos_metrics_for_owner(
                owner=key, weeks_back=weeks_back, week_of=week_of
            )
            results = list(bundle.get("metrics") or [])
        else:
            for mid in eos_metrics.METRIC_EXECUTORS:
                results.append(
                    eos_metrics.get_eos_metric(
                        mid, weeks_back=weeks_back, week_of=week_of
                    )
                )

        if as_json:
            print(json.dumps(results if len(results) != 1 else results[0], indent=2, default=str))
            return 0

        print("=" * 72)
        print("EOS metrics eyeball (read-only)")
        print(f"  ENVIRONMENT: {env}")
        print(f"  DB:          {db_hint}")
        if week_of:
            print(f"  week_of:     {week_of}")
        else:
            print(f"  weeks_back:  {weeks_back}")
        print("=" * 72)
        print()

        # Group by owner for scanning
        by_owner: dict[str, list[dict]] = {}
        for r in results:
            if r.get("error"):
                by_owner.setdefault("?", []).append(r)
                continue
            ok = r.get("scorecard_owner") or "?"
            by_owner.setdefault(ok, []).append(r)

        # Stable owner order matching scorecard walk
        order = ["David Servold", "Bill O'Neill", "Luis Solano", "Doug Ferrin", "?"]
        seen = set()
        for name in order:
            if name not in by_owner:
                continue
            seen.add(name)
            print(f"── {name} ──")
            for r in by_owner[name]:
                _print_metric(r, detail=detail)
        for name, rs in by_owner.items():
            if name in seen:
                continue
            print(f"── {name} ──")
            for r in rs:
                _print_metric(r, detail=detail)

        print("Done. Compare headlines to the scorecard export for the same Mon–Sun week.")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Eyeball EOS scorecard metrics (read-only) against the configured DB."
    )
    p.add_argument(
        "--weeks-back",
        type=int,
        default=0,
        help="0=current Mon–Sun week (default), 1=last week, …",
    )
    p.add_argument(
        "--week-of",
        type=str,
        default=None,
        help="ISO date in the desired Mon–Sun week (overrides --weeks-back).",
    )
    p.add_argument(
        "--owner",
        type=str,
        default=None,
        help="david | bill | luis | doug — only that owner's metrics.",
    )
    p.add_argument(
        "--metric",
        type=str,
        default=None,
        help="Single metric id (e.g. yellow_dates, fabrication_hours).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON instead of the human summary.",
    )
    p.add_argument(
        "--detail",
        type=int,
        default=10,
        help="Max detail rows per metric (default 10; 0 = headlines only).",
    )
    args = p.parse_args()
    return run(
        weeks_back=args.weeks_back,
        week_of=args.week_of,
        owner=args.owner,
        metric=args.metric,
        as_json=args.json,
        detail=args.detail,
    )


if __name__ == "__main__":
    raise SystemExit(main())
