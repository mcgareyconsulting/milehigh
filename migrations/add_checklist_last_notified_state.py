"""
Add the `last_notified_state` column to the `checklist_items` table.

This column is the dedup key for post-meeting to-do deadline pings: each item
fires at most one "due soon" notification and one "overdue" notification (values
'due' / 'overdue' / NULL). It replaces a time-window dedup that re-pinged every
morning because the window was shorter than the daily scan interval.

To avoid one final spurious ping when this ships, the migration backfills items
that have ALREADY been notified (last_notified_at IS NOT NULL): overdue ones to
'overdue', the rest to 'due'. Items never notified stay NULL and start fresh.

Usage:
    python migrations/add_checklist_last_notified_state.py
    python migrations/add_checklist_last_notified_state.py --database-url postgresql://...

The script is idempotent and safe to run multiple times. It inspects the current
schema before mutating and only backfills rows that still have a NULL state.
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
    """Add `last_notified_state` to checklist_items and backfill notified rows."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)
    table = "checklist_items"
    column = "last_notified_state"

    try:
        if not column_exists(engine, table, "last_notified_at"):
            print(f"✗ Table '{table}' is missing 'last_notified_at'.")
            print("  Ensure the base checklist schema exists before running this.")
            return False

        if column_exists(engine, table, column):
            print(f"✓ Column '{column}' already exists on '{table}'. Skipping add.")
        else:
            print(f"Adding column '{column}' (VARCHAR(10), nullable) to '{table}'...")
            with engine.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(10)")
                )
            print(f"✓ Added column '{column}'.")

        # Backfill rows that were already notified but have no state yet, so the new
        # state-based dedup doesn't fire one extra ping for them. CURRENT_DATE works on
        # both Postgres and SQLite; due_date is a DATE column.
        print("Backfilling notified rows with their current state...")
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    f"""
                    UPDATE {table}
                    SET {column} = CASE
                        WHEN due_date IS NOT NULL AND due_date < CURRENT_DATE THEN 'overdue'
                        ELSE 'due'
                    END
                    WHERE {column} IS NULL
                      AND last_notified_at IS NOT NULL
                    """
                )
            )
            print(f"✓ Backfilled {result.rowcount} previously-notified row(s).")

        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error during migration: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add last_notified_state column to checklist_items and backfill it."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
