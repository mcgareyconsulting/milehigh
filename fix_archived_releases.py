"""
Fix archived releases that are in the Completed Job Log CSV.

Sets stage='Complete', stage_group='COMPLETE', job_comp='X', invoiced='X'
for all is_archived=True releases found in archive-fix.csv.

Dry-run by default. Pass --commit to apply changes.

Usage:
    python fix_archived_releases.py           # dry-run
    python fix_archived_releases.py --commit  # apply changes
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


def load_csv_keys(path):
    """Load unique (job, release) pairs from the Completed Job Log CSV."""
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    keys = set()
    for row in rows[3:]:
        if not row or not row[0].strip():
            continue
        try:
            job_int = int(row[0].strip())
        except ValueError:
            continue
        release_str = row[1].strip()
        keys.add((job_int, release_str))
    return keys


def main():
    commit = "--commit" in sys.argv
    csv_path = os.path.join(os.path.dirname(__file__) or ".", "archive-fix.csv")
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    app = create_app()

    with app.app_context():
        # --- Environment info ---
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        mode = "COMMIT" if commit else "DRY-RUN"
        print("=" * 70)
        print(f"FIX ARCHIVED RELEASES — {mode}")
        print("=" * 70)
        print(f"\n  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")

        # --- Load CSV keys ---
        csv_keys = load_csv_keys(csv_path)
        print(f"  CSV entries : {len(csv_keys):,} unique (job, release) pairs")

        # --- Get archived releases in CSV ---
        archived = Releases.query.filter_by(is_archived=True).all()
        targets = [r for r in archived if (r.job, r.release) in csv_keys]
        print(f"\n  Archived releases in DB:  {len(archived):,}")
        print(f"  Matched in CSV:           {len(targets):,}")

        # --- Find which ones need changes ---
        to_update = []
        already_correct = 0

        for r in targets:
            db_sg = (r.stage_group or "").strip()
            db_stage = (r.stage or "").strip()
            db_jc = (r.job_comp or "").strip()
            db_inv = (r.invoiced or "").strip()

            needs_fix = (
                db_sg != "COMPLETE"
                or db_stage != "Complete"
                or db_jc != "X"
                or db_inv != "X"
            )

            if needs_fix:
                to_update.append((r, db_stage, db_sg, db_jc, db_inv))
            else:
                already_correct += 1

        print(f"  Already correct:          {already_correct:,}")
        print(f"  Need updating:            {len(to_update):,}")

        if not to_update:
            print("\n  Nothing to update.")
            return

        # --- Show what will change ---
        print(f"\n{'—' * 70}")
        print(f"Changes ({len(to_update)} releases):")
        print(f"{'—' * 70}")
        print(
            f"  {'Job':<7} {'Rel':<7} {'Job Name':<25} "
            f"{'Stage':<20} {'Group':<14} {'JC':<7} {'Inv':<7} {'Changes'}"
        )
        print(
            f"  {'---':<7} {'---':<7} {'--------':<25} "
            f"{'-----':<20} {'-----':<14} {'--':<7} {'---':<7} {'-------'}"
        )
        for r, db_stage, db_sg, db_jc, db_inv in sorted(
            to_update, key=lambda x: (x[0].job, x[0].release)
        ):
            changes = []
            if db_sg != "COMPLETE" or db_stage != "Complete":
                changes.append(f"stage: {db_stage or '-'} -> Complete")
            if db_jc != "X":
                changes.append(f"jc: {db_jc or '-'} -> X")
            if db_inv != "X":
                changes.append(f"inv: {db_inv or '-'} -> X")
            change_str = "; ".join(changes)
            name = (r.job_name or "")[:23]
            print(
                f"  {r.job:<7} {r.release:<7} {name:<25} "
                f"{db_stage or '-':<20} {db_sg or '-':<14} {db_jc or '-':<7} {db_inv or '-':<7} {change_str}"
            )

        # --- Apply or skip ---
        if commit:
            for r, db_stage, db_sg, db_jc, db_inv in to_update:
                r.stage = "Complete"
                r.stage_group = "COMPLETE"
                r.job_comp = "X"
                r.invoiced = "X"
            db.session.commit()
            print(f"\n  COMMITTED: {len(to_update)} releases updated.")
        else:
            print(f"\n  DRY-RUN: No changes applied. Run with --commit to apply.")
        print()


if __name__ == "__main__":
    main()
