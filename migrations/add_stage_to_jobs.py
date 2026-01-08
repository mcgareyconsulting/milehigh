"""
Add the stage column to the jobs table and populate it from existing X/O fields.

Usage:
    python migrations/add_stage_to_jobs.py

The script is idempotent and safe to run multiple times. It inspects the current
schema before attempting to alter the table, and only populates stage values that
are currently NULL.
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
        os.environ.get("DATABASE_URL"),
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
    """Perform the migration, adding stage column to jobs and populating it."""
    # Import app and models
    from app import create_app
    from app.models import Job, db
    from app.api.helpers import determine_stage_from_db_fields
    
    app = create_app()
    
    with app.app_context():
        try:
            # Use db.engine from app context to ensure same connection
            engine = db.engine
            
            # Step 1: Add the column if it doesn't exist
            if not column_exists(engine, "jobs", "stage"):
                print("Adding column 'stage' to 'jobs' table...")
                with db.engine.begin() as conn:
                    # Determine VARCHAR length based on longest stage name
                    # Longest stage name: "Store at MHMW for shipping" = 28 chars
                    # Use 128 to allow for future expansion
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN stage VARCHAR(128)"))

                # Verify column was added
                if not column_exists(engine, "jobs", "stage"):
                    print("✗ Column addition did not succeed. Please verify manually.")
                    return False
                print("✓ Successfully added 'stage' column to 'jobs'.")
            else:
                print("✓ Column 'stage' already exists on 'jobs'.")

            # Step 2: Populate stage column from existing X/O fields
            print("Populating 'stage' column from existing X/O fields...")
            
            # Get all jobs that don't have a stage set (NULL or empty)
            jobs = Job.query.filter(
                (Job.stage.is_(None)) | (Job.stage == "")
            ).all()
            
            total_jobs = len(jobs)
            print(f"Found {total_jobs} jobs to update.")
            
            if total_jobs > 0:
                updated_count = 0
                for job in jobs:
                    try:
                        # Determine stage from existing X/O fields
                        stage = determine_stage_from_db_fields(job)
                        job.stage = stage
                        updated_count += 1
                    except Exception as e:
                        print(f"  ⚠ Warning: Could not determine stage for job {job.id} ({job.job}-{job.release}): {e}")
                        # Set default stage if determination fails
                        job.stage = "Released"
                        updated_count += 1
                
                # Commit all changes
                db.session.commit()
                print(f"✓ Successfully populated stage for {updated_count} jobs.")
            else:
                print("✓ All jobs already have stage values populated.")

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
    parser = argparse.ArgumentParser(description="Add stage column to jobs table and populate it.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

