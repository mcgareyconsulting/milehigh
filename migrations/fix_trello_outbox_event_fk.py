"""
Fix trello_outbox.event_id foreign key to reference release_events (not job_events).

The FK constraint 'outbox_event_id_fkey' was created when the events table was
still called 'job_events'. After renaming to 'release_events', the FK reference
was not updated. This causes FK violations when inserting outbox rows for events
that exist in release_events but not in the stale job_events reference.

Idempotent: safe to run multiple times.
Usage:
    python migrations/fix_trello_outbox_event_fk.py
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


def infer_database_url(cli_url=None):
    candidates = [
        cli_url,
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
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


def is_postgresql(engine) -> bool:
    return engine.dialect.name == "postgresql"


def get_fk_constraints(engine, table_name: str):
    """Return FK constraints for the given table."""
    inspector = inspect(engine)
    return inspector.get_foreign_keys(table_name)


def main():
    parser = argparse.ArgumentParser(
        description="Fix trello_outbox.event_id FK to reference release_events"
    )
    parser.add_argument("--database-url", help="Database URL (default from env)")
    args = parser.parse_args()
    url = infer_database_url(args.database_url)
    print(f"Using database: {url.split('@')[-1] if '@' in url else url}")

    engine = create_engine(url)

    try:
        if not table_exists(engine, "trello_outbox"):
            print("✓ Table 'trello_outbox' does not exist; nothing to fix.")
            return

        if not is_postgresql(engine):
            print("✓ SQLite does not enforce FK constraints at this level; skipping.")
            return

        # Inspect current FK constraints on trello_outbox
        fks = get_fk_constraints(engine, "trello_outbox")
        event_fk = None
        for fk in fks:
            if "event_id" in fk.get("constrained_columns", []):
                event_fk = fk
                break

        if event_fk is None:
            print("No FK constraint found on trello_outbox.event_id.")
            # Create the correct FK
            with engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE trello_outbox '
                    'ADD CONSTRAINT outbox_event_id_fkey '
                    'FOREIGN KEY (event_id) REFERENCES release_events(id)'
                ))
            print("✓ Created FK constraint referencing release_events(id).")
            return

        referred_table = event_fk.get("referred_table", "")
        constraint_name = event_fk.get("name", "outbox_event_id_fkey")

        print(f"Found FK '{constraint_name}' on trello_outbox.event_id → {referred_table}(id)")

        if referred_table == "release_events":
            print("✓ FK already references release_events; nothing to fix.")
            return

        print(f"FK references '{referred_table}' — updating to 'release_events'...")

        # Drop old FK and add correct one (each in own transaction)
        with engine.begin() as conn:
            conn.execute(text(
                f'ALTER TABLE trello_outbox DROP CONSTRAINT "{constraint_name}"'
            ))
            print(f"✓ Dropped old FK constraint '{constraint_name}'.")

        with engine.begin() as conn:
            conn.execute(text(
                'ALTER TABLE trello_outbox '
                'ADD CONSTRAINT outbox_event_id_fkey '
                'FOREIGN KEY (event_id) REFERENCES release_events(id)'
            ))
            print("✓ Created new FK constraint referencing release_events(id).")

        print("Migration completed successfully.")

    except (OperationalError, ProgrammingError) as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
