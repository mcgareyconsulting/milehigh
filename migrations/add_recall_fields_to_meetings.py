"""
Add Recall.ai bot tracking columns to the `meetings` table:
  - meeting_url    (VARCHAR)  join link for recall-sourced meetings
  - recall_bot_id  (VARCHAR)  the dispatched Recall bot id (indexed)
  - bot_status     (VARCHAR)  bot lifecycle: scheduled|joining|in_call_recording|done|failed

Usage:
    python migrations/add_recall_fields_to_meetings.py                  # local (default)
    ENVIRONMENT=sandbox python migrations/add_recall_fields_to_meetings.py
    ENVIRONMENT=production python migrations/add_recall_fields_to_meetings.py

The target database is chosen by the app's own config (ENVIRONMENT → local sqlite /
SANDBOX_DATABASE_URL / PRODUCTION_DATABASE_URL); no manual .env handling needed.
Idempotent and safe to run multiple times — it inspects the schema before each ALTER.
"""

import argparse
import os
import sys

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add parent directory to path to import app modules
sys.path.insert(0, ROOT_DIR)

# column name -> (postgres type, sqlite type)
NEW_COLUMNS = {
    "meeting_url": ("VARCHAR(1000)", "VARCHAR(1000)"),
    "recall_bot_id": ("VARCHAR(64)", "VARCHAR(64)"),
    "bot_status": ("VARCHAR(30)", "VARCHAR(30)"),
}


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    return any(col["name"] == column_name for col in inspect(engine).get_columns(table_name))


def migrate(database_url: str = None) -> bool:
    """Add the Recall bot tracking columns + recall_bot_id index to `meetings`."""
    from app import create_app
    from app.models import db

    app = create_app()

    with app.app_context():
        try:
            # Use db.engine from app context so we hit the env-selected database.
            engine = db.engine
            is_postgres = engine.dialect.name == "postgresql"

            added = []
            for col, (pg_type, sqlite_type) in NEW_COLUMNS.items():
                if column_exists(engine, "meetings", col):
                    print(f"✓ Column '{col}' already exists on 'meetings'.")
                    continue
                col_type = pg_type if is_postgres else sqlite_type
                print(f"Adding column '{col}' ({col_type}) to 'meetings'...")
                with db.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE meetings ADD COLUMN {col} {col_type}"))
                if not column_exists(engine, "meetings", col):
                    print(f"✗ Column '{col}' addition did not succeed. Please verify manually.")
                    return False
                added.append(col)

            # Index recall_bot_id so the webhook can map an event back to a meeting.
            with db.engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_meetings_recall_bot_id "
                    "ON meetings (recall_bot_id)"
                ))

            print(f"✓ Migration completed. Added: {', '.join(added) if added else 'nothing (already current)'}.")
            return True

        except (OperationalError, ProgrammingError) as exc:
            print(f"✗ Database error: {exc}")
            db.session.rollback()
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"✗ Unexpected error: {exc}")
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add Recall bot tracking columns to the meetings table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise selected by the app via ENVIRONMENT).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
