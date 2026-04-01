"""
Compare CSV-derived stages against Trello list assignments in the Releases table.

Reads live_jobs.csv progress columns (Cut start, Fitup comp, Welded, Paint Comp,
Ship) to derive stage via rightmost-X logic, maps that to the expected Trello list,
and compares against Releases.trello_list_name in the DB.

Dry-run only — no changes are made.

Usage:
    python -m app.trello.scripts.audit_stage_vs_list
"""

import csv
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import Releases, db
from app.trello.scanner import get_expected_trello_list_from_stage


CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "live_jobs.csv")

FIELDNAMES = [
    "Job #", "Release #", "Job", "Description", "Fab Hrs", "Install HRS",
    "Paint color", "PM", "BY", "Released", "Fab Order", "Cut start",
    "Fitup comp", "Welded", "Paint Comp", "Ship",
    "Start Install", "Comp Eta", "Job Comp", "Invoiced", "Notes",
]


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


def _read_csv():
    """Read live_jobs.csv and return dict keyed by (job_int, release_str)."""
    records = {}
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f, fieldnames=FIELDNAMES)
        next(reader)  # skip header
        for row in reader:
            job = int(row["Job #"].strip())
            release = row["Release #"].strip()
            stage = _determine_stage(row)
            # Raw progress columns for display
            progress = "".join(
                "X" if row[col].strip().upper() == "X" else
                row[col].strip().upper() if row[col].strip() else "."
                for col in ["Cut start", "Fitup comp", "Welded", "Paint Comp", "Ship"]
            )
            records[(job, release)] = {
                "csv_stage": stage,
                "expected_list": get_expected_trello_list_from_stage(stage),
                "progress": progress,
            }
    return records


def audit():
    """Compare CSV-derived expected Trello list vs actual trello_list_name in DB."""
    print(f"\n{'=' * 80}")
    print("  CSV STAGE vs TRELLO LIST AUDIT")
    print(f"{'=' * 80}")
    print(f"  Database: {db.engine.url}")

    csv_records = _read_csv()
    print(f"  CSV records: {len(csv_records)}")

    releases = Releases.query.filter(Releases.is_archived == False).all()
    rel_by_key = {(r.job, str(r.release)): r for r in releases}
    print(f"  Active Releases: {len(releases)}")

    matched_keys = set(csv_records.keys()) & set(rel_by_key.keys())
    print(f"  Matched: {len(matched_keys)}")

    mismatches = []
    no_trello_list = []
    correct = 0

    for key in sorted(matched_keys):
        csv_info = csv_records[key]
        rel = rel_by_key[key]
        expected_list = csv_info["expected_list"]
        actual_list = rel.trello_list_name

        if not actual_list:
            no_trello_list.append((rel, csv_info))
            continue

        if expected_list != actual_list:
            mismatches.append((rel, csv_info, actual_list))
        else:
            correct += 1

    print(f"\n  Correct:            {correct}")
    print(f"  Mismatched:         {len(mismatches)}")
    print(f"  No Trello list:     {len(no_trello_list)}")

    if mismatches:
        print(f"\n  MISMATCHES ({len(mismatches)}):")
        print(f"  {'Job-Rel':<14} {'Progress':<10} {'CSV Stage':<28} {'Expected List':<28} {'Actual List'}")
        print("  " + "-" * 108)
        for rel, csv_info, actual_list in mismatches:
            print(
                f"  {rel.job}-{rel.release:<8} "
                f"{csv_info['progress']:<10} "
                f"{csv_info['csv_stage'][:26]:<28} "
                f"{(csv_info['expected_list'] or '?')[:26]:<28} "
                f"{actual_list}"
            )

    if no_trello_list:
        print(f"\n  NO TRELLO LIST IN DB ({len(no_trello_list)}):")
        print(f"  {'Job-Rel':<14} {'Progress':<10} {'CSV Stage':<28} {'Expected List'}")
        print("  " + "-" * 80)
        for rel, csv_info in no_trello_list:
            print(
                f"  {rel.job}-{rel.release:<8} "
                f"{csv_info['progress']:<10} "
                f"{csv_info['csv_stage'][:26]:<28} "
                f"{csv_info['expected_list'] or '?'}"
            )

    print(f"\n{'=' * 80}\n")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        audit()
