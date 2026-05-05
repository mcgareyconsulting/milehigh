"""
Drop the unique constraint/index on submittal_events.payload_hash.

Content-based dedup at the event layer was suppressing legitimate human
actions whose payloads happened to match (value oscillating back through
the same string). Burst dedup at the receipt layer is the correct place
to dedup; payload_hash stays as a forensic column.

Reverses migrations/add_unique_payload_hash_submittal_events.py.

Usage:
    python migrations/drop_unique_payload_hash_submittal_events.py
    python migrations/drop_unique_payload_hash_submittal_events.py --database-url sqlite:///instance/jobs.sqlite
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


def constraint_exists(engine, table_name: str, constraint_name: str, is_sqlite: bool) -> bool:
    with engine.connect() as conn:
        if is_sqlite:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=:name"
            ), {"name": constraint_name})
            return result.fetchone() is not None
    inspector = inspect(engine)
    for c in inspector.get_unique_constraints(table_name):
        if c.get("name") == constraint_name:
            return True
    for idx in inspector.get_indexes(table_name):
        if idx.get("name") == constraint_name and idx.get("unique"):
            return True
    return False


def migrate(database_url=None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    connect_args = {}
    if "postgresql" in db_url.lower():
        connect_args["connect_timeout"] = 10

    engine = create_engine(db_url, connect_args=connect_args)
    constraint_name = "uq_submittal_events_payload_hash"

    try:
        if not table_exists(engine, "submittal_events"):
            print("✗ Table 'submittal_events' does not exist. Nothing to do.")
            return False

        is_sqlite = "sqlite" in db_url.lower()

        if not constraint_exists(engine, "submittal_events", constraint_name, is_sqlite):
            print(f"✓ Constraint '{constraint_name}' does not exist. Nothing to do.")
            return True

        with engine.begin() as conn:
            if is_sqlite:
                conn.execute(text(f"DROP INDEX IF EXISTS {constraint_name}"))
            else:
                # The original migration used ALTER TABLE ... ADD CONSTRAINT,
                # which creates a backing unique index of the same name. Try
                # constraint drop first, fall back to index drop.
                try:
                    conn.execute(text(
                        f"ALTER TABLE submittal_events DROP CONSTRAINT IF EXISTS {constraint_name}"
                    ))
                except (OperationalError, ProgrammingError):
                    conn.execute(text(f"DROP INDEX IF EXISTS {constraint_name}"))
            print(f"✓ Dropped '{constraint_name}'.")

        print("✓ Migration completed successfully.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error during migration: {exc}")
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
        description="Drop unique constraint on submittal_events.payload_hash."
    )
    parser.add_argument("--database-url", help="Override database URL")
    args = parser.parse_args()
    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
