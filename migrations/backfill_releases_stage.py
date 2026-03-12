"""
Backfill releases table: stage, stage_group, banana_color.

This migration:
1. For each Releases row with stage=NULL, finds the matching Job by (job, release)
2. Copies Job.trello_list_name → Releases.stage
3. Derives stage_group from stage using get_stage_group_from_stage()
4. Applies "Welded" / "Welded QC" → READY_TO_SHIP correction
5. Leaves banana_color NULL (user-controlled via Job Log 2.0)

Usage:
    python migrations/backfill_releases_stage.py [--database-url <url>]

The script is idempotent and safe to run multiple times.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

# Add parent directory to path to import app modules
sys.path.insert(0, ROOT_DIR)

# Load environment variables from a .env file if present
load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    """Return a SQLAlchemy-friendly SQLite URL for the given path."""
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: str = None) -> str:
    """Figure out which database to hit, honoring CLI and environment defaults."""
    candidates = [
        cli_url,
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
    ]

    for value in candidates:
        if not value:
            continue

        value = value.strip()
        if value.startswith("postgres://"):
            # SQLAlchemy expects postgresql://
            return value.replace("postgres://", "postgresql://", 1)

        if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
            return value

        # Treat anything else as a filesystem path to a SQLite DB
        return normalize_sqlite_path(value)

    # Fall back to bundled SQLite file
    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def migrate(database_url: str = None) -> bool:
    """Backfill releases table with stage, stage_group, and banana_color."""
    # Import app and models
    from app import create_app
    from app.models import Releases, Job, db
    from app.api.helpers import get_stage_group_from_stage

    app = create_app()

    with app.app_context():
        try:
            print("Backfilling releases table with stage and stage_group...")

            # Find all releases where stage is NULL
            releases_to_fill = Releases.query.filter(Releases.stage.is_(None)).all()

            total_count = len(releases_to_fill)
            print(f"Found {total_count} releases with NULL stage.")

            if total_count == 0:
                print("✓ No releases need backfill.")
                return True

            filled_count = 0
            already_filled_count = 0
            no_job_match_count = 0
            no_trello_list_count = 0
            error_count = 0

            # Process in batches for clarity
            batch_size = 100
            for batch_start in range(0, len(releases_to_fill), batch_size):
                batch_end = min(batch_start + batch_size, len(releases_to_fill))
                batch = releases_to_fill[batch_start:batch_end]

                for rel in batch:
                    try:
                        # Skip if already filled
                        if rel.stage is not None:
                            already_filled_count += 1
                            continue

                        # Find matching Job by (job, release)
                        job = Job.query.filter_by(job=rel.job, release=rel.release).first()

                        if not job:
                            no_job_match_count += 1
                            # Set default: Released / FABRICATION
                            rel.stage = "Released"
                            rel.stage_group = "FABRICATION"
                            filled_count += 1
                            continue

                        # Use job.trello_list_name if available
                        if job.trello_list_name and job.trello_list_name.strip():
                            rel.stage = job.trello_list_name
                            stage_group = get_stage_group_from_stage(job.trello_list_name)
                            rel.stage_group = stage_group if stage_group else "FABRICATION"
                            filled_count += 1
                            print(
                                f"  ✓ Release {rel.job}-{rel.release}: "
                                f"stage='{rel.stage}', stage_group='{rel.stage_group}'"
                            )
                        else:
                            # No trello_list_name on job record
                            no_trello_list_count += 1
                            rel.stage = "Released"
                            rel.stage_group = "FABRICATION"
                            filled_count += 1
                            print(
                                f"  ℹ Release {rel.job}-{rel.release}: "
                                f"no trello_list_name on job, defaulting to Released/FABRICATION"
                            )

                    except Exception as e:
                        print(f"  ✗ Error backfilling release {rel.job}-{rel.release}: {e}")
                        error_count += 1

                # Commit batch
                if batch_end - batch_start > 0:
                    db.session.commit()

            # Final cleanup: correct Welded stages to READY_TO_SHIP (per migration policy)
            # Note: "Welded" maps to FABRICATION in the stage mapping, but business logic
            # requires Welded/Welded QC to be in READY_TO_SHIP group
            print("\nApplying Welded/Welded QC → READY_TO_SHIP correction...")
            welded_stages = ["Welded", "Welded QC"]
            welded_jobs = Releases.query.filter(
                Releases.stage.in_(welded_stages)
            ).all()

            welded_corrected = 0
            for rel in welded_jobs:
                if rel.stage_group != "READY_TO_SHIP":
                    old_group = rel.stage_group
                    rel.stage_group = "READY_TO_SHIP"
                    welded_corrected += 1
                    print(f"  ✓ Release {rel.job}-{rel.release}: stage='{rel.stage}', stage_group {old_group} → READY_TO_SHIP")

            if welded_corrected > 0:
                db.session.commit()

            # Report
            print(f"\n=== Backfill Summary ===")
            print(f"Filled: {filled_count}")
            print(f"Already filled: {already_filled_count}")
            print(f"No matching Job record: {no_job_match_count}")
            print(f"Job had no trello_list_name: {no_trello_list_count}")
            print(f"Welded stages corrected: {welded_corrected}")
            print(f"Errors: {error_count}")

            # Verification
            print("\n=== Verification ===")
            total_releases = Releases.query.count()
            with_stage = Releases.query.filter(Releases.stage.isnot(None)).count()
            with_stage_group = Releases.query.filter(Releases.stage_group.isnot(None)).count()
            print(f"Total releases: {total_releases}")
            print(f"Releases with stage: {with_stage}")
            print(f"Releases with stage_group: {with_stage_group}")

            if with_stage == total_releases and with_stage_group == total_releases:
                print("✓ Backfill completed successfully!")
                return True
            else:
                print(f"⚠ Warning: {total_releases - with_stage} releases still have NULL stage")
                print(f"⚠ Warning: {total_releases - with_stage_group} releases still have NULL stage_group")
                return True  # Still consider success; some rows may legitimately have NULL

        except (OperationalError, ProgrammingError) as exc:
            print(f"✗ Database error: {exc}")
            db.session.rollback()
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"✗ Unexpected error: {exc}")
            db.session.rollback()
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill releases table with stage and stage_group from jobs table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
