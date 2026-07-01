"""
@milehigh-header
schema_version: 1
purpose: Reconcile ball-in-court for tracked submittals against the Procore API to
         backfill updates that were never delivered during a webhook emission outage.
exports:
  TARGET_PROJECTS: Default (project_number, project_id) pairs to reconcile.
  reconcile_project: Diff+optionally apply BIC for every tracked submittal in one project.
  main: CLI entry point (dry-run by default; --execute to write).
imports_from: [app, app.models, app.procore.client, app.procore.procore]
imported_by: []
invariants:
  - Requires Flask app context (creates its own via create_app).
  - Invoked directly as `python -m app.procore.scripts.reconcile_bic`.
  - DRY-RUN by default: no writes unless --execute is passed.
  - Surgical: on --execute updates ONLY ball_in_court + last_bic_update/last_updated.
    Does NOT replay webhook side-effects (no Trello sync, urgency bump, order compression)
    and does NOT emit SubmittalEvents — it is a silent data backfill.
  - Parses BIC via handle_submittal_update, i.e. identically to the live webhook path.
  - Never starts the APScheduler (pops IS_RENDER_SCHEDULER before create_app).

Why this exists
---------------
Procore stopped emitting Submittals webhooks company-wide at 2026-06-30 21:37 UTC, so
ball-in-court changes made in Procore after that point were never written to our DB.
This script re-reads the current state from Procore (source of truth) for the affected
projects and rectifies stale ball_in_court values.

Usage
-----
    # DRY-RUN (default) — report drift, change nothing
    ENVIRONMENT=production python -m app.procore.scripts.reconcile_bic

    # APPLY the ball_in_court updates
    ENVIRONMENT=production python -m app.procore.scripts.reconcile_bic --execute

    # Limit to one project number, or write a JSON report
    ENVIRONMENT=production python -m app.procore.scripts.reconcile_bic --project 600
    ENVIRONMENT=production python -m app.procore.scripts.reconcile_bic --execute --report /tmp/bic_reconcile.json
"""

import argparse
import json
import os
from datetime import datetime

# The reconcile only ever runs one process; never let create_app() boot the
# background scheduler (Trello drainer, calendar poll, etc.) against prod.
os.environ.pop("IS_RENDER_SCHEDULER", None)
os.environ.pop("WERKZEUG_RUN_MAIN", None)

from app import create_app
from app.models import db, Submittals
from app.procore.client import get_procore_client
from app.procore.procore import handle_submittal_update


# (project_number, project_id) — the projects knocked out by the webhook outage.
TARGET_PROJECTS = [
    ("600", "3468202"),  # Hines - Retreat at Longmont
    ("630", "3575130"),  # Altera Rogers Road
]


def _norm(value):
    """Match the webhook's own comparison: None is treated as empty string, no trimming."""
    return value if value is not None else ""


def reconcile_project(project_number, project_id, execute=False, include_status=False):
    """
    Diff (and optionally apply) ball_in_court — and, with include_status, status —
    for every tracked submittal in a project.

    Returns a result dict with per-submittal rows and summary counts.
    """
    client = get_procore_client()
    result = {
        "project_number": project_number,
        "project_id": project_id,
        "include_status": include_status,
        "scanned": 0,
        "not_tracked": 0,
        "fetch_failed": 0,
        "in_sync": 0,
        "bic_drift": 0,
        "bic_updated": 0,
        "status_drift": 0,
        "status_updated": 0,
        "rows": [],   # only rows with drift / problems worth showing
    }

    try:
        submittals = client.get_submittals(int(project_id)) or []
    except Exception as e:
        result["error"] = f"Failed to list submittals from Procore: {e}"
        return result

    changed_any = False
    for s in submittals:
        sid = s.get("id")
        if sid is None:
            continue
        result["scanned"] += 1

        # Re-read + parse exactly as a live webhook update would.
        try:
            parsed = handle_submittal_update(int(project_id), sid)
        except Exception as e:
            result["fetch_failed"] += 1
            result["rows"].append({
                "submittal_id": str(sid), "action": "fetch_error", "detail": str(e),
            })
            continue

        if parsed is None:
            result["fetch_failed"] += 1
            result["rows"].append({
                "submittal_id": str(sid), "action": "fetch_error",
                "detail": "handle_submittal_update returned None (unparseable)",
            })
            continue

        record, procore_bic, _approvers, procore_status, procore_title, _mgr = parsed

        if record is None:
            # Exists in Procore but never ingested into our DB — out of scope for a
            # field backfill (we don't create rows here). Surface it so it isn't silent.
            result["not_tracked"] += 1
            result["rows"].append({
                "submittal_id": str(sid),
                "title": procore_title,
                "action": "not_in_db",
                "procore_bic": procore_bic,
                "procore_status": procore_status,
            })
            continue

        bic_drift = _norm(record.ball_in_court) != _norm(procore_bic)
        status_drift = _norm(record.status) != _norm(procore_status)

        if bic_drift:
            result["bic_drift"] += 1
        if status_drift:
            result["status_drift"] += 1
        if not bic_drift and not status_drift:
            result["in_sync"] += 1
            continue

        row = {
            "submittal_id": str(sid),
            "title": record.title,
            "bic_drift": bic_drift,
            "status_drift": status_drift,
            "db_bic": record.ball_in_court,
            "procore_bic": procore_bic,
            "db_status": record.status,
            "procore_status": procore_status,
            "status_applied": False,
            "last_updated_before": record.last_updated.isoformat() if record.last_updated else None,
            "action": "would_update",
        }

        if execute:
            applied = False
            if bic_drift:
                record.ball_in_court = procore_bic
                record.last_bic_update = datetime.utcnow()
                result["bic_updated"] += 1
                applied = True
            if status_drift and include_status:
                record.status = procore_status
                # Mirror the webhook path: a submittal that is no longer Open must not
                # hold an ordering slot (check_and_update_submittal does the same).
                if _norm(procore_status) != "Open" and record.order_number is not None:
                    record.order_number = None
                result["status_updated"] += 1
                row["status_applied"] = True
                applied = True
            if applied:
                record.last_updated = datetime.utcnow()
                changed_any = True
                row["action"] = "updated"

        result["rows"].append(row)

    if execute and changed_any:
        db.session.commit()

    return result


def _print_report(results, execute, include_status):
    mode = "EXECUTE (writing changes)" if execute else "DRY-RUN (no changes)"
    scope = "BIC + status" if include_status else "BIC only"
    print(f"\n=== submittal reconcile [{scope}] — {mode} ===\n")

    grand = {"scanned": 0, "bic_drift": 0, "bic_updated": 0,
             "status_drift": 0, "status_updated": 0, "not_tracked": 0, "fetch_failed": 0}
    for r in results:
        print(f"Project {r['project_number']} (id {r['project_id']})")
        if r.get("error"):
            print(f"  ERROR: {r['error']}\n")
            continue
        print(f"  scanned={r['scanned']}  in_sync={r['in_sync']}  "
              f"BIC_drift={r['bic_drift']} (updated={r['bic_updated']})  "
              f"status_drift={r['status_drift']} (updated={r['status_updated']})  "
              f"not_in_db={r['not_tracked']}  fetch_failed={r['fetch_failed']}")

        for row in r["rows"]:
            if row["action"] in ("would_update", "updated"):
                tag = "✓ UPDATED" if row["action"] == "updated" else "→ would update"
                title = (row.get("title") or "")[:45]
                print(f"    {tag}  {row['submittal_id']}  {title!r}")
                if row.get("bic_drift"):
                    print(f"        BIC:    {row['db_bic']!r}  ->  {row['procore_bic']!r}")
                if row.get("status_drift"):
                    if include_status:
                        note = "" if (execute and row.get("status_applied")) else ""
                    else:
                        note = "   (not applied — pass --include-status)"
                    print(f"        status: {row['db_status']!r}  ->  {row['procore_status']!r}{note}")
            elif row["action"] == "not_in_db":
                title = (row.get("title") or "")[:45]
                print(f"    ! not tracked in DB: {row['submittal_id']}  {title!r} "
                      f"(Procore BIC={row.get('procore_bic')!r})")
            elif row["action"] == "fetch_error":
                print(f"    ✗ fetch error: {row['submittal_id']} — {row.get('detail')}")

        print()
        for k in grand:
            grand[k] += r.get(k, 0)

    print("--- totals ---")
    print(f"  scanned={grand['scanned']}  "
          f"BIC_drift={grand['bic_drift']} (updated={grand['bic_updated']})  "
          f"status_drift={grand['status_drift']} (updated={grand['status_updated']})  "
          f"not_in_db={grand['not_tracked']}  fetch_failed={grand['fetch_failed']}")
    if not execute:
        pending = grand["bic_drift"] + (grand["status_drift"] if include_status else 0)
        if pending:
            what = "ball-in-court/status" if include_status else "ball-in-court"
            print(f"\n  Re-run with --execute to apply {what} updates "
                  f"({grand['bic_drift']} BIC" +
                  (f", {grand['status_drift']} status" if include_status else "") + ").")
        if not include_status and grand["status_drift"]:
            print(f"  Note: {grand['status_drift']} submittal(s) also have status drift — "
                  f"add --include-status to reconcile those too.")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile submittal ball-in-court from Procore for projects hit by the webhook outage."
    )
    parser.add_argument("--execute", action="store_true",
                        help="Apply updates. Omit for a dry-run (default).")
    parser.add_argument("--include-status", action="store_true",
                        help="Also reconcile status drift (e.g. Draft->Open), mirroring the "
                             "webhook's status handling. Default: ball_in_court only.")
    parser.add_argument("--project", metavar="NUMBER",
                        help="Limit to a single project number (e.g. 600). Default: all target projects.")
    parser.add_argument("--report", metavar="PATH",
                        help="Write the full result (including in-sync counts) as JSON to PATH.")
    args = parser.parse_args()

    targets = TARGET_PROJECTS
    if args.project:
        targets = [t for t in TARGET_PROJECTS if t[0] == args.project]
        if not targets:
            parser.error(f"--project {args.project} is not a known target project "
                         f"({', '.join(n for n, _ in TARGET_PROJECTS)})")

    app = create_app()
    with app.app_context():
        results = [
            reconcile_project(num, pid, execute=args.execute, include_status=args.include_status)
            for num, pid in targets
        ]

    _print_report(results, args.execute, args.include_status)

    if args.report:
        with open(args.report, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Wrote JSON report to {args.report}")


if __name__ == "__main__":
    main()
