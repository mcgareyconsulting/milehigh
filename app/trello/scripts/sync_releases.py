"""
Sync the Releases table to match live_jobs.csv exactly.

Ensures all 300 CSV records are active in the DB. Creates missing rows,
un-archives previously archived rows, and archives rows not in the CSV.

Usage:
    python -m app.trello.scripts.sync_releases [--dry-run]
"""

import argparse
import csv
import os

from dotenv import load_dotenv

load_dotenv()

from datetime import datetime

from app import create_app
from app.models import Releases, db
from app.api.helpers import get_stage_group_from_stage, DEFAULT_FAB_ORDER


CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "final-boss.csv")


def _parse_float(val):
    """Parse a float from a string, returning None on failure."""
    val = val.strip() if val else ""
    try:
        return float(val) if val else None
    except ValueError:
        return None


def _parse_date(val):
    """Parse a date like '7/29' or '11/14' into a date object (current year)."""
    val = val.strip() if val else ""
    if not val:
        return None
    try:
        dt = datetime.strptime(val, "%m/%d")
        return dt.replace(year=datetime.now().year).date()
    except ValueError:
        return None


def _determine_stage(row):
    """Derive stage from CSV progress columns using rightmost-X logic."""
    ship = row["Ship"].strip().upper()
    if ship == "ST":
        return "Store at MHMW for shipping"
    if ship == "RS":
        return "Shipping planning"

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


FIELDNAMES = [
    "Job #", "Release #", "Job", "Description", "Fab Hrs", "Install HRS",
    "Paint color", "PM", "BY", "Released", "Fab Order", "Cut start",
    "Fitup comp", "Welded", "Paint Comp", "Ship",
    "Start Install", "Comp Eta", "Job Comp", "Invoiced", "Notes",
]


def _read_csv():
    """Read live_jobs.csv and return dict keyed by (job_int, release_str)."""
    records = {}
    with open(CSV_PATH, newline="") as f:
        # Override headers since the CSV has unnamed trailing columns
        reader = csv.DictReader(f, fieldnames=FIELDNAMES)
        next(reader)  # skip the original header row
        for row in reader:
            job = int(row["Job #"].strip())
            release = row["Release #"].strip()
            stage = _determine_stage(row)
            records[(job, release)] = {
                "job_name": row["Job"].strip(),
                "description": row["Description"].strip(),
                "fab_hrs": _parse_float(row.get("Fab Hrs", "")),
                "install_hrs": _parse_float(row.get("Install HRS", "")),
                "paint_color": row.get("Paint color", "").strip() or None,
                "pm": row.get("PM", "").strip() or None,
                "by": row.get("BY", "").strip() or None,
                "released": _parse_date(row.get("Released", "")),
                "fab_order": _parse_float(row.get("Fab Order", "")) or DEFAULT_FAB_ORDER,
                "stage": stage,
                "stage_group": get_stage_group_from_stage(stage),
                "start_install": _parse_date(row.get("Start Install", "")),
                "comp_eta": _parse_date(row.get("Comp Eta", "")),
                "job_comp": (row.get("Job Comp", "").strip()) or None,
                "invoiced": (row.get("Invoiced", "").strip()) or None,
                "notes": (row.get("Notes", "").strip()) or None,
            }
    return records


CSV_FIELDS = [
    "job_name", "description", "fab_hrs", "install_hrs", "paint_color",
    "pm", "by", "released", "fab_order", "stage", "stage_group",
    "start_install", "comp_eta", "job_comp", "invoiced", "notes",
]


def _apply_csv_fields(release, info):
    """Update a Releases row with all fields from the CSV record."""
    for f in CSV_FIELDS:
        setattr(release, f, info[f])


def sync(dry_run=False):
    """Ensure exactly the CSV's 300 records are active in the Releases table."""
    print(f"\n{'=' * 70}")
    print("  SYNC RELEASES FROM CSV")
    print(f"{'=' * 70}")
    print(f"  Database: {db.engine.url}")
    if dry_run:
        print("  Mode: DRY RUN (no changes will be made)")

    csv_records = _read_csv()
    csv_keys = set(csv_records.keys())
    print(f"\n  CSV records: {len(csv_keys)}")

    # All releases in the DB (active and archived)
    all_releases = Releases.query.all()
    all_by_key = {(r.job, str(r.release)): r for r in all_releases}
    all_keys = set(all_by_key.keys())

    active_keys = {k for k, r in all_by_key.items() if not r.is_archived}
    archived_keys = {k for k, r in all_by_key.items() if r.is_archived}

    print(f"  Total Releases in DB:     {len(all_releases)}")
    print(f"  Currently active:         {len(active_keys)}")
    print(f"  Currently archived:       {len(archived_keys)}")

    # 1. Un-archive: in CSV and in DB but archived
    to_unarchive = csv_keys & archived_keys
    # 2. Create: in CSV but not in DB at all
    to_create = csv_keys - all_keys
    # 3. Archive: active in DB but not in CSV
    to_archive = active_keys - csv_keys

    # Report
    if to_unarchive:
        print(f"\n  Un-archiving {len(to_unarchive)} previously archived releases:")
        print("  " + "-" * 60)
        for job, rel in sorted(to_unarchive):
            r = all_by_key[(job, rel)]
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"    {prefix}{job}-{rel:<8} {(r.job_name or '')[:30]}")

    if to_create:
        print(f"\n  Creating {len(to_create)} new releases:")
        print("  " + "-" * 60)
        for job, rel in sorted(to_create):
            info = csv_records[(job, rel)]
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"    {prefix}{job}-{rel:<8} {info['job_name'][:30]:<32} {info['description'][:25]}")

    if to_archive:
        print(f"\n  Archiving {len(to_archive)} releases not in CSV:")
        print("  " + "-" * 60)
        for job, rel in sorted(to_archive, key=lambda k: (k[0], k[1])):
            r = all_by_key[(job, rel)]
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"    {prefix}{job}-{rel:<8} {(r.job_name or '')[:30]:<32} stage={r.stage or '(none)'}")

    if not to_unarchive and not to_create and not to_archive:
        print(f"\n  Already in sync. Nothing to do.")

    # Apply
    if not dry_run:
        for key in to_unarchive:
            r = all_by_key[key]
            r.is_archived = False
            _apply_csv_fields(r, csv_records[key])
        for key in to_archive:
            all_by_key[key].is_archived = True
        for key in to_create:
            info = csv_records[key]
            db.session.add(Releases(
                job=key[0],
                release=key[1],
                is_archived=False,
                **{f: info[f] for f in CSV_FIELDS},
            ))
        # Also update existing active releases with latest CSV data
        for key in (csv_keys & active_keys):
            _apply_csv_fields(all_by_key[key], csv_records[key])
        if to_unarchive or to_create or to_archive or (csv_keys & active_keys):
            db.session.commit()

    # Final count
    final_count = Releases.query.filter(Releases.is_archived == False).count()
    print(f"\n  Active Releases after sync: {final_count}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Releases table from live_jobs.csv")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        sync(dry_run=args.dry_run)
