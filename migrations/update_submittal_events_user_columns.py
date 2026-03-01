"""
Update submittal_events: rename user_id -> internal_user_id, add external_user_id, drop user_name.

Idempotent. Safe to run after add_user_name_to_submittal_events.

Usage:
    python migrations/update_submittal_events_user_columns.py
    python migrations/update_submittal_events_user_columns.py --database-url sqlite:///instance/jobs.sqlite
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


def infer_database_url(cli_url=None) -> str:
    candidates = [
        cli_url,
        os.environ.get("JOBS_SQLITE_PATH"),
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("DATABASE_URL"),
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


def table_exists(engine, table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(database_url=None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    connect_args = {}
    if "postgresql" in db_url.lower():
        connect_args["connect_timeout"] = 10

    engine = create_engine(db_url, connect_args=connect_args)

    try:
        if not table_exists(engine, "submittal_events"):
            print("✗ Table 'submittal_events' does not exist. Nothing to do.")
            return False

        # Read schema once, outside any DDL transaction (avoids holding locks)
        has_user_id = column_exists(engine, "submittal_events", "user_id")
        has_internal_user_id = column_exists(engine, "submittal_events", "internal_user_id")
        has_external_user_id = column_exists(engine, "submittal_events", "external_user_id")
        has_user_name = column_exists(engine, "submittal_events", "user_name")

        def run_pg_timeout(conn):
            """Set 30s statement timeout for this connection (Postgres). Ignore if not allowed."""
            if "postgresql" not in db_url.lower():
                return
            try:
                conn.execute(text("SET statement_timeout = '30s'"))
            except Exception:
                pass  # proceed without timeout if server rejects it

        # 1. Rename user_id -> internal_user_id (one short transaction)
        if has_user_id and not has_internal_user_id:
            print("Renaming column 'user_id' to 'internal_user_id'...")
            with engine.begin() as conn:
                run_pg_timeout(conn)
                conn.execute(text("ALTER TABLE submittal_events RENAME COLUMN user_id TO internal_user_id"))
            print("✓ Renamed user_id -> internal_user_id.")
        elif has_user_id and has_internal_user_id:
            print("(Skip rename: both user_id and internal_user_id exist; run SQL manually if needed)")

        # 2. Add external_user_id (one short transaction)
        if not has_external_user_id:
            print("Adding column 'external_user_id'...")
            with engine.begin() as conn:
                run_pg_timeout(conn)
                conn.execute(text("ALTER TABLE submittal_events ADD COLUMN external_user_id VARCHAR(255)"))
            print("✓ Added external_user_id.")

        # 3. Drop user_name (one short transaction)
        if has_user_name:
            print("Dropping column 'user_name'...")
            with engine.begin() as conn:
                run_pg_timeout(conn)
                conn.execute(text("ALTER TABLE submittal_events DROP COLUMN user_name"))
            print("✓ Dropped user_name.")

        print("✓ Migration completed successfully.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update submittal_events: user_id -> internal_user_id, add external_user_id, drop user_name."
    )
    parser.add_argument("--database-url", help="Database URL")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
