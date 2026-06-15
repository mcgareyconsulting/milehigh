"""
Add owner-inference columns to the `checklist_items` table:
  - owner_inferred      (BOOLEAN)  owner was inferred from a matched job, not stated
  - matched_job_number  (VARCHAR)  the active job a to-do was matched to (display tag)

(`confidence` is reused to hold the match confidence, so no column is added for it.)

Usage:
    python migrations/add_owner_inference_to_checklist_items.py                  # local
    ENVIRONMENT=sandbox python migrations/add_owner_inference_to_checklist_items.py
    ENVIRONMENT=production python migrations/add_owner_inference_to_checklist_items.py

Target DB is chosen by the app's config (ENVIRONMENT). Idempotent — inspects first.
"""

import argparse
import os
import sys

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

NEW_COLUMNS = {
    "owner_inferred": ("BOOLEAN", "BOOLEAN"),
    "matched_job_number": ("VARCHAR(32)", "VARCHAR(32)"),
    "matched_job_name": ("VARCHAR(128)", "VARCHAR(128)"),
    "match_source": ("VARCHAR(16)", "VARCHAR(16)"),
    "name_corrected": ("BOOLEAN", "BOOLEAN"),
}


def column_exists(engine, table_name, column_name):
    return any(c["name"] == column_name for c in inspect(engine).get_columns(table_name))


def migrate(database_url=None):
    from app import create_app
    from app.models import db

    app = create_app()
    with app.app_context():
        try:
            engine = db.engine
            is_postgres = engine.dialect.name == "postgresql"
            added = []
            for col, (pg_type, sqlite_type) in NEW_COLUMNS.items():
                if column_exists(engine, "checklist_items", col):
                    print(f"✓ Column '{col}' already exists on 'checklist_items'.")
                    continue
                col_type = pg_type if is_postgres else sqlite_type
                is_bool = pg_type.upper().startswith("BOOLEAN")
                default = ((" DEFAULT false" if is_postgres else " DEFAULT 0") if is_bool else "")
                print(f"Adding column '{col}' ({col_type}) to 'checklist_items'...")
                with db.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE checklist_items ADD COLUMN {col} {col_type}{default}"))
                if not column_exists(engine, "checklist_items", col):
                    print(f"✗ Column '{col}' addition did not succeed. Verify manually.")
                    return False
                added.append(col)
            print(f"✓ Migration completed. Added: {', '.join(added) if added else 'nothing (already current)'}.")
            return True
        except (OperationalError, ProgrammingError) as exc:
            print(f"✗ Database error: {exc}")
            db.session.rollback()
            return False
        except Exception as exc:  # pragma: no cover
            print(f"✗ Unexpected error: {exc}")
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add owner-inference columns to checklist_items.")
    parser.add_argument("--database-url", help="Override DB URL (otherwise selected by ENVIRONMENT).")
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
