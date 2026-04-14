"""
@milehigh-header
schema_version: 1
purpose: Push stage and fab_order values from the live_jobs_more.csv spreadsheet into the Releases table.
exports:
  sync_from_csv: Compare live_jobs_more.csv against active Releases and update stage + fab_order.
  _determine_stage: Derive stage from CSV progress columns using rightmost-X logic.
  _read_csv: Read live_jobs_more.csv and return dict keyed by (job_int, release_str).
imports_from: [app, app.models, app.api.helpers, csv, dotenv, argparse]
imported_by: []
invariants:
  - Supports --dry-run to preview without committing.
  - Requires Flask app context (created via create_app at __main__).
  - Invoked directly: python -m app.trello.scripts.sync_from_csv [--dry-run]
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Sync Release stages and fab_order from live_jobs_more.csv.

Reads the CSV's progress columns (Cut start, Fitup comp, Welded, Paint Comp,
Ship) to derive stage via rightmost-X logic, then updates non-archived Releases
rows to match.

Usage:
    python -m app.trello.scripts.sync_from_csv [--dry-run]
"""

import argparse
import csv
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import Releases, db
from app.api.helpers import get_stage_group_from_stage


CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "live_jobs_more.csv")


def _read_csv():
    """Read live_jobs_more.csv and return dict keyed by (job_int, release_str)."""
    records = {}
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            job = int(row["Job #"].strip())
            release = row["Release #"].strip()
            stage = _determine_stage(row)
            fab_order_raw = row["Fab Order"].strip()
            try:
                fab_order = float(fab_order_raw) if fab_order_raw else None
            except ValueError:
                fab_order = None
            records[(job, release)] = {
                "stage": stage,
                "fab_order": fab_order,
                "job_name": row["Job"].strip(),
                "description": row["Description"].strip(),
            }
    return records


def _determine_stage(row):
    """Derive stage from CSV progress columns using rightmost-X logic.

    Special Ship column values: ST -> Store at MHMW for shipping,
    RS -> Shipping planning. Otherwise, the rightmost column with 'X'
    determines the stage.
    """
    ship = row["Ship"].strip().upper()
    if ship == "ST":
        return "Store at MHMW for shipping"
    if ship == "RS":
        return "Shipping planning"

    # Check columns right-to-left for rightmost X
    columns = [
        ("Ship", "Shipping completed"),
        ("Paint Comp", "Paint complete"),
        ("Welded", "Welded"),
        ("Fitup comp", "Fit Up Complete."),
        ("Cut start", "Cut start"),
    ]
    for col, stage in columns:
        if row[col].strip().upper() == "X":
            return stage

    return "Released"


def sync_from_csv(dry_run=False):
    """Compare live_jobs_more.csv against active Releases and update stage + fab_order."""
    print("\n--- Sync Releases from live_jobs_more.csv ---")
    print(f"  Database: {db.engine.url}")

    csv_records = _read_csv()
    print(f"  CSV records: {len(csv_records)}")

    releases = Releases.query.filter(Releases.is_archived == False).all()
    print(f"  Non-archived Releases: {len(releases)}")

    # Build lookup
    rel_by_key = {}
    for rel in releases:
        rel_by_key[(rel.job, str(rel.release))] = rel

    csv_keys = set(csv_records.keys())
    db_keys = set(rel_by_key.keys())
    matched_keys = csv_keys & db_keys
    in_csv_not_db = csv_keys - db_keys
    in_db_not_csv = db_keys - csv_keys

    print(f"  Matched: {len(matched_keys)}")
    print(f"  In CSV but not in Releases: {len(in_csv_not_db)}")
    print(f"  In Releases but not in CSV: {len(in_db_not_csv)}")

    if in_csv_not_db:
        print(f"\n  CSV records missing from Releases:")
        print("  " + "-" * 55)
        for job, rel in sorted(in_csv_not_db, key=lambda k: (k[0], k[1])):
            info = csv_records[(job, rel)]
            print(f"    {job}-{rel:<8} {info['job_name'][:30]}")

    if in_db_not_csv:
        print(f"\n  Active Releases not in CSV:")
        print("  " + "-" * 55)
        for job, rel in sorted(in_db_not_csv, key=lambda k: (int(k[0]), k[1])):
            r = rel_by_key[(job, rel)]
            print(f"    {job}-{rel:<8} {(r.job_name or '')[:30]}")

    # Diff stage
    stage_changes = []
    for key in sorted(matched_keys, key=lambda k: (k[0], k[1])):
        rel = rel_by_key[key]
        csv_stage = csv_records[key]["stage"]
        db_stage = rel.stage or "(none)"
        if db_stage != csv_stage:
            stage_changes.append((rel, db_stage, csv_stage))

    print(f"\n--- Stage updates ---")
    if stage_changes:
        print(f"  {'Job-Rel':<14} {'Current Stage':<30} {'CSV Stage':<30}")
        print("  " + "-" * 74)
        for rel, db_stage, csv_stage in stage_changes:
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"  {prefix}{rel.job}-{rel.release:<8} {db_stage:<30} -> {csv_stage:<30}")
    print(f"  Stage changes: {len(stage_changes)}")

    # Diff fab_order
    fab_changes = []
    for key in sorted(matched_keys, key=lambda k: (k[0], k[1])):
        rel = rel_by_key[key]
        csv_fab = csv_records[key]["fab_order"]
        if csv_fab is not None and rel.fab_order != csv_fab:
            fab_changes.append((rel, rel.fab_order, csv_fab))

    print(f"\n--- Fab Order updates ---")
    if fab_changes:
        print(f"  {'Job-Rel':<14} {'Current':<14} {'CSV':<14}")
        print("  " + "-" * 42)
        for rel, old_val, new_val in fab_changes:
            prefix = "[DRY RUN] " if dry_run else ""
            old_str = str(old_val) if old_val is not None else "None"
            print(f"  {prefix}{rel.job}-{rel.release:<8} {old_str:<14} -> {new_val}")
    print(f"  Fab Order changes: {len(fab_changes)}")

    # Apply
    if dry_run:
        print(f"\n  [DRY RUN] No changes applied.")
        return

    for rel, _old, csv_stage in stage_changes:
        rel.stage = csv_stage
        rel.stage_group = get_stage_group_from_stage(csv_stage)

    for rel, _old, csv_fab in fab_changes:
        rel.fab_order = csv_fab

    db.session.commit()
    print(f"\n  Updated {len(stage_changes)} stages and {len(fab_changes)} fab orders.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Release stages and fab_order from live_jobs_more.csv")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        sync_from_csv(dry_run=args.dry_run)
