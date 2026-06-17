"""
Migration: pre/post-meeting Brain snapshots + agreed-update reconciliation.

Add columns to `meetings`:
  - pre_snapshot   (JSON) job-log/DWL field values of the discussed entities at meeting START
  - post_snapshot  (JSON) the same fields at meeting END (when extraction runs)

Add columns to `checklist_items`:
  - expected_update       (JSON)    a field change the room agreed to make to the Brain
                                     ({target, field, new_value}), set by the extractor
  - brain_update_pending  (BOOLEAN) True when that agreed update never landed on the Brain
                                     by meeting end — a recommended "you forgot to update
                                     the Brain" action for the super user

Idempotent — inspects before altering. Mirrors migrations/add_meeting_summary_and_ended_at.py.

Run with:
    python migrations/add_meeting_snapshots_and_brain_update.py                  # local (default)
    ENVIRONMENT=sandbox python migrations/add_meeting_snapshots_and_brain_update.py
    ENVIRONMENT=production python migrations/add_meeting_snapshots_and_brain_update.py
"""

import argparse
import os
import sys

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# table -> {column: (postgres type, sqlite type)}
NEW_COLUMNS = {
    "meetings": {
        "pre_snapshot": ("JSON", "JSON"),
        "post_snapshot": ("JSON", "JSON"),
    },
    "checklist_items": {
        "expected_update": ("JSON", "JSON"),
        "brain_update_pending": ("BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
    },
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
            for table, cols in NEW_COLUMNS.items():
                for col, (pg_type, sqlite_type) in cols.items():
                    if _column_exists(engine, table, col):
                        print(f"✓ Column '{col}' already exists on '{table}'.")
                        continue
                    col_type = pg_type if is_postgres else sqlite_type
                    print(f"Adding column '{col}' ({col_type}) to '{table}'...")
                    with db.engine.begin() as conn:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                    if not _column_exists(engine, table, col):
                        print(f"✗ Column '{col}' addition did not succeed. Verify manually.")
                        return False
                    added.append(f"{table}.{col}")

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
        description="Add meeting snapshots + checklist brain-update reconciliation columns.")
    parser.add_argument("--database-url",
                        help="Override database URL (otherwise selected via ENVIRONMENT).")
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
