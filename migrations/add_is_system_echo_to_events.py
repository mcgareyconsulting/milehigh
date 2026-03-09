"""
Add is_system_echo column to submittal_events and release_events tables.

This flag marks webhook events that are echoes of our own API calls (e.g. a Procore
webhook fired in response to Brain updating a submittal status). Echo events are
recorded in the DB for debugging but hidden in the Events UI by default.

Usage:
    python migrations/add_is_system_echo_to_events.py

The script is idempotent and safe to run multiple times.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: str = None) -> str:
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
            return value.replace("postgres://", "postgresql://", 1)
        if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
            return value
        return normalize_sqlite_path(value)
    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def column_exists(engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def table_exists(engine, table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def add_column(engine, table_name: str, column_name: str, db_url: str) -> bool:
    """Add a boolean is_system_echo column (NOT NULL DEFAULT FALSE) to the given table."""
    if not table_exists(engine, table_name):
        print(f"✗ Table '{table_name}' does not exist. Skipping.")
        return False

    if column_exists(engine, table_name, column_name):
        print(f"✓ Column '{column_name}' already exists on '{table_name}'. Nothing to do.")
        return True

    print(f"Adding column '{column_name}' to '{table_name}'...")
    with engine.begin() as conn:
        if "postgresql" in db_url or "postgres" in db_url:
            conn.execute(text(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        else:
            # SQLite does not support NOT NULL without a default on ADD COLUMN
            conn.execute(text(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} BOOLEAN NOT NULL DEFAULT 0"
            ))
    print(f"✓ Added '{column_name}' to '{table_name}'.")
    return True


def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)

    try:
        ok1 = add_column(engine, "submittal_events", "is_system_echo", db_url)
        ok2 = add_column(engine, "release_events", "is_system_echo", db_url)
        return ok1 and ok2
    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc}")
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add is_system_echo column to submittal_events and release_events."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()
    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
