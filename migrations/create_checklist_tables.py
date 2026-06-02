"""
Migration: create the meeting-checklist tables (meetings, checklist_items) and add
the checklist_item_id FK to notifications.

Idempotent — safe to re-run. Mirrors migrations/create_board_tables.py.

Run with:
    python migrations/create_checklist_tables.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app import create_app
from app.models import db, Meeting, ChecklistItem  # noqa: F401 (imported so create_all sees them)


def _table_exists(name: str) -> bool:
    return name in inspect(db.engine).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(db.engine).get_columns(table))


def migrate() -> bool:
    app = create_app()
    with app.app_context():
        try:
            # 1. New tables (create_all only creates what's missing)
            if _table_exists("meetings") and _table_exists("checklist_items"):
                print("✓ Tables 'meetings' and 'checklist_items' already exist.")
            else:
                print("Creating checklist tables...")
                db.create_all()
                if not (_table_exists("meetings") and _table_exists("checklist_items")):
                    print("✗ ERROR: checklist tables were not created")
                    return False
                print("✓ Created 'meetings' and 'checklist_items'")

            # 2. Add notifications.checklist_item_id if missing (simple ADD COLUMN works on SQLite + PG)
            if _column_exists("notifications", "checklist_item_id"):
                print("✓ notifications.checklist_item_id already present.")
            else:
                print("Adding notifications.checklist_item_id ...")
                with db.engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE notifications ADD COLUMN checklist_item_id INTEGER"
                    ))
                if _column_exists("notifications", "checklist_item_id"):
                    print("✓ Added notifications.checklist_item_id")
                else:
                    print("✗ ERROR: column was not added")
                    return False

            return True
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    sys.exit(0 if migrate() else 1)
