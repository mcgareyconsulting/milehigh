"""
Add the cut_start, fitup_comp, welded, paint_comp, and ship columns to the jobs table.

These columns replace the old 'stage' column and track individual stage completion dates.

Usage:
    python migrations/add_job_stage_columns.py

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
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(database_url: str = None) -> bool:
    """Perform the migration, adding stage columns to jobs if needed."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        inspector = inspect(engine)
        if not inspector.has_table("jobs"):
            print("✗ Table 'jobs' does not exist. Nothing to do.")
            return False

        # Columns to add: cut_start, fitup_comp, welded, paint_comp, ship
        columns_to_add = [
            ("cut_start", "VARCHAR(8)"),
            ("fitup_comp", "VARCHAR(8)"),
            ("welded", "VARCHAR(8)"),
            ("paint_comp", "VARCHAR(8)"),
            ("ship", "VARCHAR(8)"),
        ]

        missing_columns = []
        for col_name, col_type in columns_to_add:
            if not column_exists(engine, "jobs", col_name):
                missing_columns.append((col_name, col_type))
            else:
                print(f"✓ Column '{col_name}' already exists on 'jobs'.")

        if not missing_columns:
            print("✓ All stage columns already exist on 'jobs'. Nothing to do.")
            return True

        print(f"Adding {len(missing_columns)} column(s) to 'jobs' table...")
        with engine.begin() as conn:
            for col_name, col_type in missing_columns:
                print(f"  Adding column '{col_name}'...")
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}"))

        # Re-check to confirm all columns were added
        all_added = True
        for col_name, _ in missing_columns:
            if column_exists(engine, "jobs", col_name):
                print(f"✓ Successfully added '{col_name}' column to 'jobs'.")
            else:
                print(f"✗ Column '{col_name}' addition did not succeed. Please verify manually.")
                all_added = False

        if all_added:
            print("\n✓ Migration completed successfully!")
            return True

        print("\n✗ Some columns were not added. Please verify manually.")
        return False

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error while adding columns: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add stage columns (cut_start, fitup_comp, welded, paint_comp, ship) to jobs table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

