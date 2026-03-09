"""
Add unique constraint on payload_hash to release_events table.

SubmittalEvents already had this constraint. ReleaseEvents was missing it,
leaving a race window where concurrent Trello webhook threads could both pass
the application-level duplicate check and insert duplicate events.

Usage:
    python migrations/add_unique_payload_hash_release_events.py

Idempotent — safe to run multiple times.
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


def constraint_exists(engine, table_name: str, constraint_name: str) -> bool:
    inspector = inspect(engine)
    unique_constraints = inspector.get_unique_constraints(table_name)
    return any(c["name"] == constraint_name for c in unique_constraints)


def table_exists(engine, table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)

    constraint_name = "uq_release_events_payload_hash"
    table_name = "release_events"

    try:
        if not table_exists(engine, table_name):
            print(f"✗ Table '{table_name}' does not exist. Nothing to do.")
            return False

        if constraint_exists(engine, table_name, constraint_name):
            print(f"✓ Constraint '{constraint_name}' already exists. Nothing to do.")
            return True

        print(f"Adding unique constraint '{constraint_name}' on '{table_name}.payload_hash'...")

        db_url_lower = str(db_url).lower()
        with engine.begin() as conn:
            if "postgresql" in db_url_lower or "postgres" in db_url_lower:
                # First remove any existing duplicates (keep lowest id per hash)
                conn.execute(text("""
                    DELETE FROM release_events
                    WHERE id NOT IN (
                        SELECT MIN(id) FROM release_events GROUP BY payload_hash
                    )
                """))
                conn.execute(text(f"""
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT {constraint_name} UNIQUE (payload_hash)
                """))
            else:
                # SQLite: recreate via index (ALTER TABLE ADD CONSTRAINT not supported)
                conn.execute(text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {constraint_name} ON {table_name}(payload_hash)"
                ))

        print(f"✓ Constraint '{constraint_name}' added successfully.")
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
    parser = argparse.ArgumentParser(
        description="Add unique constraint on payload_hash to release_events."
    )
    parser.add_argument("--database-url", help="Override database URL.")
    args = parser.parse_args()
    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
