"""
Add a composite index on the (id, last_updated_at) columns to the jobs table.

This migration improves query performance when filtering or sorting jobs by both
id and last_updated_at together.

Usage:
    python migrations/add_index_on_jobs_last_updated_at.py

The script is idempotent and safe to run multiple times. It inspects the current
schema before attempting to create the index.
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


def index_exists(engine, table_name: str, index_name: str) -> bool:
    """Check if a given index exists on the specified table."""
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(database_url: str = None) -> bool:
    """Perform the migration, adding index on last_updated_at to jobs if needed."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)
    index_name = "idx_jobs_id_last_updated_at"

    try:
        # Check if columns exist first
        if not column_exists(engine, "jobs", "id"):
            print("✗ Column 'id' does not exist on 'jobs' table.")
            print("  Please ensure the column exists before adding an index.")
            return False

        if not column_exists(engine, "jobs", "last_updated_at"):
            print("✗ Column 'last_updated_at' does not exist on 'jobs' table.")
            print("  Please ensure the column exists before adding an index.")
            return False

        if index_exists(engine, "jobs", index_name):
            print(f"✓ Index '{index_name}' already exists on 'jobs'. Nothing to do.")
            return True

        print(f"Adding composite index '{index_name}' on (id, last_updated_at) columns to 'jobs' table...")
        with engine.begin() as conn:
            # Create composite index on (id, last_updated_at)
            # Using IF NOT EXISTS for databases that support it (PostgreSQL 9.5+)
            # For SQLite, we check first, so this should be safe
            conn.execute(text(f"CREATE INDEX {index_name} ON jobs (id, last_updated_at)"))

        # Re-check to confirm
        if index_exists(engine, "jobs", index_name):
            print(f"✓ Successfully added index '{index_name}' to 'jobs' table.")
            return True

        print("✗ Index creation did not succeed. Please verify manually.")
        return False

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error while adding index: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add composite index on (id, last_updated_at) columns to jobs table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

