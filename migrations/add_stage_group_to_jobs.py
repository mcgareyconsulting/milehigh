"""
Add the stage_group column to the jobs table and populate it based on stage values.

Usage:
    python migrations/add_stage_group_to_jobs.py

The script is idempotent and safe to run multiple times. It inspects the current
schema before attempting to alter the table, and populates stage_group values
based on the stage field using the STAGE_TO_GROUP mapping.
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
        # os.environ.get("DATABASE_URL"),
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


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(database_url: str = None) -> bool:
    """Perform the migration, adding stage_group column to jobs and populating it."""
    # Import app and models
    from app import create_app
    from app.models import Job, db
    from app.api.helpers import get_stage_group_from_stage
    
    app = create_app()
    
    with app.app_context():
        try:
            # Use db.engine from app context to ensure same connection
            engine = db.engine
            
            # Step 1: Add the column if it doesn't exist
            if not column_exists(engine, "jobs", "stage_group"):
                print("Adding column 'stage_group' to 'jobs' table...")
                with db.engine.begin() as conn:
                    # Use VARCHAR(64) to accommodate group names like "READY_TO_SHIP"
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN stage_group VARCHAR(64)"))

                # Verify column was added
                if not column_exists(engine, "jobs", "stage_group"):
                    print("✗ Column addition did not succeed. Please verify manually.")
                    return False
                print("✓ Successfully added 'stage_group' column to 'jobs'.")
            else:
                print("✓ Column 'stage_group' already exists on 'jobs'.")

            # Step 2: Populate stage_group column from stage values
            print("Populating 'stage_group' column from 'stage' values...")
            
            # Get all jobs that have a stage but no stage_group
            jobs = Job.query.filter(
                Job.stage.isnot(None),
                (Job.stage_group.is_(None)) | (Job.stage_group == "")
            ).all()
            
            total_jobs = len(jobs)
            print(f"Found {total_jobs} jobs to update.")
            
            if total_jobs > 0:
                updated_count = 0
                unmapped_count = 0
                for job in jobs:
                    try:
                        # Get stage_group from stage
                        stage_group = get_stage_group_from_stage(job.stage)
                        if stage_group:
                            job.stage_group = stage_group
                            updated_count += 1
                        else:
                            # Stage not in mapping - log warning but don't fail
                            print(f"  ⚠ Warning: Stage '{job.stage}' for job {job.job}-{job.release} is not mapped to a stage_group")
                            unmapped_count += 1
                    except Exception as e:
                        print(f"  ⚠ Warning: Could not determine stage_group for job {job.id} ({job.job}-{job.release}): {e}")
                        unmapped_count += 1
                
                # Commit all changes
                db.session.commit()
                print(f"✓ Successfully populated stage_group for {updated_count} jobs.")
                if unmapped_count > 0:
                    print(f"  ⚠ {unmapped_count} jobs had unmapped stages (stage_group left as NULL).")
            else:
                print("✓ All jobs already have stage_group values populated or have no stage value.")

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
    parser = argparse.ArgumentParser(description="Add stage_group column to jobs table and populate it.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)


