"""
Add notes column and remove ball_in_court_due_date column from procore_submittals table.

Usage:
    python migrations/update_procore_submittals_notes.py

The script is idempotent and safe to run multiple times. It inspects the current
schema before attempting to alter the table.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

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


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate(database_url: str = None) -> bool:
    """Perform the migration, adding notes and removing ball_in_court_due_date if needed."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        if not table_exists(engine, "procore_submittals"):
            print("✗ Table 'procore_submittals' does not exist. Nothing to do.")
            return False

        # Check column existence BEFORE starting transaction to avoid lock conflicts
        notes_exists = column_exists(engine, "procore_submittals", "notes")
        ball_in_court_due_date_exists = column_exists(engine, "procore_submittals", "ball_in_court_due_date")

        # Determine if we need to make any changes
        needs_changes = not notes_exists or ball_in_court_due_date_exists

        if not needs_changes:
            print("✓ Column 'notes' already exists and 'ball_in_court_due_date' does not exist. Nothing to do.")
            return True

        # Now start transaction only if we need to make changes
        with engine.begin() as conn:
            # Add notes column if it doesn't exist
            if not notes_exists:
                print("Adding column 'notes' to 'procore_submittals' table...")
                conn.execute(text("ALTER TABLE procore_submittals ADD COLUMN notes TEXT"))
                print("✓ Successfully added 'notes' column.")
            else:
                print("✓ Column 'notes' already exists. Skipping.")

            # Remove ball_in_court_due_date column if it exists
            if ball_in_court_due_date_exists:
                print("Removing column 'ball_in_court_due_date' from 'procore_submittals' table...")
                # Check if we're using PostgreSQL (supports DROP COLUMN)
                db_url_lower = str(db_url).lower()
                if "postgresql" in db_url_lower or "postgres" in db_url_lower:
                    conn.execute(text("ALTER TABLE procore_submittals DROP COLUMN ball_in_court_due_date"))
                    print("✓ Successfully removed 'ball_in_court_due_date' column.")
                else:
                    # SQLite doesn't support DROP COLUMN directly
                    print("⚠ Note: SQLite doesn't support DROP COLUMN directly.")
                    print("⚠ You may need to manually remove the column or use a table recreation strategy.")
                    print("⚠ For now, the column will remain but won't be used by the application.")
            else:
                print("✓ Column 'ball_in_court_due_date' does not exist. Nothing to remove.")

        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc}")
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add notes column and remove ball_in_court_due_date from procore_submittals table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

