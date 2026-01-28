"""
Update stage_group for 'Welded' and 'Welded QC' stages to READY_TO_SHIP.

This migration updates all jobs that have 'Welded' or 'Welded QC' as their stage
to have stage_group = 'READY_TO_SHIP' instead of 'FABRICATION'.

Usage:
    python migrations/update_welded_stages_to_ready_to_ship.py

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
    """Update stage_group for 'Welded' and 'Welded QC' stages to READY_TO_SHIP."""
    # Import app and models
    from app import create_app
    from app.models import Job, db
    from app.api.helpers import get_stage_group_from_stage
    
    app = create_app()
    
    with app.app_context():
        try:
            # Stages that need to be updated
            stages_to_update = ['Welded', 'Welded QC']
            target_stage_group = 'READY_TO_SHIP'
            
            print(f"Updating stage_group for stages: {', '.join(stages_to_update)} to '{target_stage_group}'...")
            
            # Find all jobs with these stages
            jobs_to_update = Job.query.filter(
                Job.stage.in_(stages_to_update)
            ).all()
            
            total_jobs = len(jobs_to_update)
            print(f"Found {total_jobs} jobs to update.")
            
            if total_jobs == 0:
                print("✓ No jobs found with 'Welded' or 'Welded QC' stages.")
                return True
            
            updated_count = 0
            already_correct_count = 0
            error_count = 0
            
            for job in jobs_to_update:
                try:
                    # Verify the stage_group should be READY_TO_SHIP using the mapping
                    expected_stage_group = get_stage_group_from_stage(job.stage)
                    
                    if expected_stage_group != target_stage_group:
                        print(f"  ⚠ Warning: Stage '{job.stage}' for job {job.job}-{job.release} maps to '{expected_stage_group}', not '{target_stage_group}'. Skipping.")
                        error_count += 1
                        continue
                    
                    # Check if already correct
                    if job.stage_group == target_stage_group:
                        already_correct_count += 1
                        continue
                    
                    # Update the stage_group
                    old_stage_group = job.stage_group
                    job.stage_group = target_stage_group
                    updated_count += 1
                    
                    print(f"  ✓ Updated job {job.job}-{job.release}: stage='{job.stage}', stage_group: '{old_stage_group}' -> '{target_stage_group}'")
                    
                except Exception as e:
                    print(f"  ✗ Error updating job {job.job}-{job.release}: {e}")
                    error_count += 1
            
            # Commit all changes
            if updated_count > 0:
                db.session.commit()
                print(f"\n✓ Successfully updated stage_group for {updated_count} jobs.")
            else:
                print(f"\n✓ No updates needed.")
            
            if already_correct_count > 0:
                print(f"  ℹ {already_correct_count} jobs already had correct stage_group.")
            
            if error_count > 0:
                print(f"  ⚠ {error_count} jobs had errors or unexpected mappings.")
            
            print("✓ Migration completed successfully.")
            return True

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
        description="Update stage_group for 'Welded' and 'Welded QC' stages to READY_TO_SHIP."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

