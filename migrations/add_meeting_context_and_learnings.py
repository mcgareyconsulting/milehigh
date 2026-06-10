"""
Migration: pre-meeting context + the learnings loop.

1. Add columns to `meetings`:
   - agenda_text       (TEXT)      pasted agenda / pre-meeting notes (the "before" view)
   - context_snapshot  (TEXT)      event-state block shown to the extractor at generation
   - learned_at        (TIMESTAMP) when the learnings step last ran
2. Create new tables (db.create_all only builds what's missing):
   - meeting_learnings   per-meeting synthesized insight + usage meter
   - extraction_signals  reusable cross-meeting feedback (alias|owner_map|pattern)

Idempotent — inspects before altering. Mirrors migrations/add_extract_usage_to_meetings.py
and migrations/create_checklist_tables.py.

Run with:
    python migrations/add_meeting_context_and_learnings.py                  # local (default)
    ENVIRONMENT=sandbox python migrations/add_meeting_context_and_learnings.py
    ENVIRONMENT=production python migrations/add_meeting_context_and_learnings.py
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
    "agenda_text": ("TEXT", "TEXT"),
    "context_snapshot": ("TEXT", "TEXT"),
    "learned_at": ("TIMESTAMP", "DATETIME"),
}


def _column_exists(engine, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(engine).get_columns(table))


def _table_exists(engine, name: str) -> bool:
    return name in inspect(engine).get_table_names()


def migrate(database_url: str = None) -> bool:
    # Imported so db.create_all() sees the new mappers.
    from app import create_app
    from app.models import db, MeetingLearning, ExtractionSignal  # noqa: F401

    app = create_app()
    with app.app_context():
        try:
            engine = db.engine
            is_postgres = engine.dialect.name == "postgresql"

            # 1. Add the new meetings columns.
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

            # 2. Create the new tables (create_all only builds what's missing).
            if _table_exists(engine, "meeting_learnings") and _table_exists(engine, "extraction_signals"):
                print("✓ Tables 'meeting_learnings' and 'extraction_signals' already exist.")
            else:
                print("Creating learnings tables...")
                db.create_all()
                if not (_table_exists(engine, "meeting_learnings")
                        and _table_exists(engine, "extraction_signals")):
                    print("✗ ERROR: learnings tables were not created")
                    return False
                print("✓ Created 'meeting_learnings' and 'extraction_signals'")

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
        description="Add pre-meeting context columns + the learnings tables.")
    parser.add_argument("--database-url",
                        help="Override database URL (otherwise selected via ENVIRONMENT).")
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
