"""
Add external_user_id and internal_user_id to release_events.

- external_user_id: Trello/Procore user ID from webhook
- internal_user_id: Rename from user_id for consistency with submittal_events;
  resolved via users.trello_id (or users.procore_id) lookup

Idempotent. Safe to run multiple times.

Usage:
    python migrations/add_external_user_id_to_release_events.py
    python migrations/add_external_user_id_to_release_events.py --database-url sqlite:///instance/jobs.sqlite
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
        if not table_exists(engine, "release_events"):
            print("✗ Table 'release_events' does not exist. Nothing to do.")
            return False

        has_external_user_id = column_exists(engine, "release_events", "external_user_id")
        has_user_id = column_exists(engine, "release_events", "user_id")
        has_internal_user_id = column_exists(engine, "release_events", "internal_user_id")

        def run_pg_timeout(conn):
            """Set 30s statement timeout for this connection (Postgres). Ignore if not allowed."""
            if "postgresql" not in db_url.lower():
                return
            try:
                conn.execute(text("SET statement_timeout = '30s'"))
            except Exception:
                pass

        if not has_external_user_id:
            print("Adding column 'external_user_id' to release_events...")
            with engine.begin() as conn:
                run_pg_timeout(conn)
                conn.execute(text("ALTER TABLE release_events ADD COLUMN external_user_id VARCHAR(255)"))
            print("✓ Added external_user_id.")
        else:
            print("(Skip: external_user_id already exists)")

        # Rename user_id -> internal_user_id for consistency with submittal_events
        if has_user_id and not has_internal_user_id:
            print("Renaming column 'user_id' to 'internal_user_id'...")
            with engine.begin() as conn:
                run_pg_timeout(conn)
                conn.execute(text("ALTER TABLE release_events RENAME COLUMN user_id TO internal_user_id"))
            print("✓ Renamed user_id -> internal_user_id.")
        elif has_user_id and has_internal_user_id:
            print("(Skip rename: both user_id and internal_user_id exist)")
        elif not has_user_id and not has_internal_user_id:
            print("(Skip rename: neither user_id nor internal_user_id exists)")

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
        description="Add external_user_id and rename user_id->internal_user_id in release_events."
    )
    parser.add_argument("--database-url", help="Database URL")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
