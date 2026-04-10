"""
Compare archived releases in the database against the Completed Job Log CSV.

Finds releases that are archived in the DB but NOT present in the CSV,
which may have been accidentally archived.

Usage:
    python check_archived_releases.py
"""
import csv
import os
import sys
from urllib.parse import urlparse, urlunparse

from app import create_app
from app.models import Releases, db


def redact_uri(uri):
    """Redact password from a database URI for safe logging."""
    try:
        parsed = urlparse(uri)
        if parsed.password:
            replaced = parsed._replace(
                netloc=f"{parsed.username}:***@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(replaced)
    except Exception:
        pass
    return uri


def load_csv(path):
    """Load unique (job, release) pairs from the Completed Job Log CSV.

    Returns:
        tuple: (set of (job_int, release_str) pairs, total_data_rows, skipped_count)
    """
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    pairs = set()
    total_data_rows = 0
    skipped = []

    for row in rows[3:]:  # skip metadata, date header, column headers
        if not row or not row[0].strip():
            continue
        job_str = row[0].strip()
        release_str = row[1].strip()
        total_data_rows += 1

        try:
            job_int = int(job_str)
        except ValueError:
            skipped.append((job_str, release_str))
            continue

        pairs.add((job_int, release_str))

    if skipped:
        print(f"  Skipped {len(skipped)} rows with non-numeric Job #:")
        for job_str, rel in skipped:
            print(f"    Job #{job_str}, Release #{rel}")

    return pairs, total_data_rows, len(skipped)


def main():
    csv_path = os.path.join(os.path.dirname(__file__) or ".", "archive-fix.csv")
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    app = create_app()

    with app.app_context():
        # --- DB info ---
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        print("=" * 60)
        print("ARCHIVE CHECK — DB vs CSV Comparison")
        print("=" * 60)
        print(f"\n  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")

        # --- CSV ---
        print(f"\n{'—' * 60}")
        print("CSV: Completed Job Log (archive-fix.csv)")
        print(f"{'—' * 60}")
        csv_pairs, total_rows, skipped = load_csv(csv_path)
        print(f"  Total data rows       : {total_rows:,}")
        print(f"  Unique (job, release)  : {len(csv_pairs):,}")

        # --- DB archived releases ---
        print(f"\n{'—' * 60}")
        print("DB: Archived Releases (is_archived=True)")
        print(f"{'—' * 60}")
        archived = Releases.query.filter_by(is_archived=True).all()
        archived_dict = {(r.job, r.release): r for r in archived}
        print(f"  Archived releases     : {len(archived_dict):,}")

        # --- Comparison ---
        db_keys = set(archived_dict.keys())
        suspects = db_keys - csv_pairs       # archived in DB, not in CSV
        csv_only = csv_pairs - db_keys       # in CSV, not archived in DB
        overlap = db_keys & csv_pairs        # in both

        print(f"\n{'—' * 60}")
        print("Comparison Results")
        print(f"{'—' * 60}")
        print(f"  In both DB archived & CSV : {len(overlap):,}")
        print(f"  Archived in DB, NOT in CSV: {len(suspects):,}  <-- SUSPECTS")
        print(f"  In CSV, NOT archived in DB: {len(csv_only):,}")

        # --- Suspect details ---
        if suspects:
            print(f"\n{'=' * 60}")
            print("SUSPECT RELEASES (archived in DB but not in CSV)")
            print(f"{'=' * 60}")
            print(f"  {'Job':<8} {'Release':<10} {'Job Name':<40} {'Description'}")
            print(f"  {'---':<8} {'-------':<10} {'--------':<40} {'-----------'}")
            for key in sorted(suspects):
                r = archived_dict[key]
                desc = (r.description or "")[:60]
                name = (r.job_name or "")[:38]
                print(f"  {r.job:<8} {r.release:<10} {name:<40} {desc}")
        else:
            print("\n  All DB-archived releases are accounted for in the CSV.")

        print()


if __name__ == "__main__":
    main()
