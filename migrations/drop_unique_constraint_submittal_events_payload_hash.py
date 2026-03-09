"""
Drop the unique constraint on submittal_events.payload_hash.

Deduplication is now handled by the webhook_receipts table (burst dedup)
and the with_for_update() row lock in check_and_update_submittal().
The payload_hash column is retained for auditing but no longer needs
to be unique — the same field transition can legitimately recur in
Procore workflow cycles (e.g. Drafter -> PM -> Drafter -> PM).

Usage:
    python migrations/drop_unique_constraint_submittal_events_payload_hash.py
    python migrations/drop_unique_constraint_submittal_events_payload_hash.py --database-url postgresql://...

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


def infer_database_url(cli_url=None):
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
        if value.startswith(("postgresql://", "mysql://", "sqlite://")):
            return value
        return f"sqlite:///{os.path.join(ROOT_DIR, value) if not os.path.isabs(value) else value}"
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


def constraint_exists(engine, table_name, constraint_name):
    for c in inspect(engine).get_unique_constraints(table_name):
        if c.get("name") == constraint_name:
            return True
    return False


def migrate(database_url=None):
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)

    constraint_name = "uq_submittal_events_payload_hash"

    try:
        if not constraint_exists(engine, "submittal_events", constraint_name):
            print(f"✓ Constraint '{constraint_name}' does not exist. Nothing to do.")
            return True

        is_pg = "postgresql" in db_url.lower()

        with engine.begin() as conn:
            if is_pg:
                conn.execute(text(
                    f"ALTER TABLE submittal_events DROP CONSTRAINT {constraint_name}"
                ))
            else:
                # SQLite doesn't support DROP CONSTRAINT — drop the index
                conn.execute(text(f"DROP INDEX IF EXISTS {constraint_name}"))

        print(f"✓ Constraint '{constraint_name}' dropped successfully.")
        return True

    except (OperationalError, ProgrammingError) as e:
        print(f"✗ Database error: {e}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Drop unique constraint on submittal_events.payload_hash."
    )
    parser.add_argument("--database-url", help="Override database URL.")
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
