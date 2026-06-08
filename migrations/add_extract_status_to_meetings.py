"""
Add background-extraction tracking columns to the `meetings` table:
  - extract_status      (VARCHAR)   idle|extracting|done|failed (default 'idle')
  - extract_error       (TEXT)      last failure message, if extraction failed
  - extract_started_at  (TIMESTAMP) when the current/last extraction run began

These back the on-demand "Generate to-do list" flow, which now runs the (multi-minute)
LLM extraction in a background thread and returns 202 — the UI polls extract_status
instead of holding the request open past gunicorn's worker timeout.

Usage:
    python migrations/add_extract_status_to_meetings.py                  # local (default)
    ENVIRONMENT=sandbox python migrations/add_extract_status_to_meetings.py
    ENVIRONMENT=production python migrations/add_extract_status_to_meetings.py

Target DB is chosen by the app's config (ENVIRONMENT → local sqlite /
SANDBOX_DATABASE_URL / PRODUCTION_DATABASE_URL). Idempotent — inspects before altering.
"""

import argparse
import os
import sys

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# column name -> (postgres type, sqlite type)
NEW_COLUMNS = {
    "extract_status": ("VARCHAR(20) DEFAULT 'idle'", "VARCHAR(20) DEFAULT 'idle'"),
    "extract_error": ("TEXT", "TEXT"),
    "extract_started_at": ("TIMESTAMP", "TIMESTAMP"),
}


def column_exists(engine, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in inspect(engine).get_columns(table_name))


def migrate(database_url: str = None) -> bool:
    from app import create_app
    from app.models import db

    app = create_app()
    with app.app_context():
        try:
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
        description="Add background-extraction tracking columns to the meetings table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise selected by the app via ENVIRONMENT).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
