"""
Migration: meeting summary output + meeting-end timestamp.

Add columns to `meetings`:
  - summary    (TEXT)      the generated meeting summary (events-during-runtime + transcript),
                           the second output a meeting produces alongside the to-do checklist
  - ended_at   (TIMESTAMP) meeting end (stamped when the Recall transcript is pulled / the bot
                           leaves); bounds the "events during meeting" window for the summary

Idempotent — inspects before altering. Mirrors migrations/add_meeting_context_and_learnings.py.

Run with:
    python migrations/add_meeting_summary_and_ended_at.py                  # local (default)
    ENVIRONMENT=sandbox python migrations/add_meeting_summary_and_ended_at.py
    ENVIRONMENT=production python migrations/add_meeting_summary_and_ended_at.py
"""

import argparse
import os
import sys

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# column name -> (postgres type, sqlite type)
NEW_MEETING_COLUMNS = {
    "summary": ("TEXT", "TEXT"),
    "ended_at": ("TIMESTAMP", "DATETIME"),
}


def _column_exists(engine, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(engine).get_columns(table))


def migrate(database_url: str = None) -> bool:
    from app import create_app
    from app.models import db

    app = create_app()
    with app.app_context():
        try:
            engine = db.engine
            is_postgres = engine.dialect.name == "postgresql"

            added = []
            for col, (pg_type, sqlite_type) in NEW_MEETING_COLUMNS.items():
                if _column_exists(engine, "meetings", col):
                    print(f"✓ Column '{col}' already exists on 'meetings'.")
                    continue
                col_type = pg_type if is_postgres else sqlite_type
                print(f"Adding column '{col}' ({col_type}) to 'meetings'...")
                with db.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE meetings ADD COLUMN {col} {col_type}"))
                if not _column_exists(engine, "meetings", col):
                    print(f"✗ Column '{col}' addition did not succeed. Verify manually.")
                    return False
                added.append(col)

            print(f"✓ Migration completed. Columns added: "
                  f"{', '.join(added) if added else 'none (already current)'}.")
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
        description="Add the meeting summary + ended_at columns.")
    parser.add_argument("--database-url",
                        help="Override database URL (otherwise selected via ENVIRONMENT).")
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
