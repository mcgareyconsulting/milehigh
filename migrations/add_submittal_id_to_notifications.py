"""Migration to add submittal_id column to notifications for DWL @mentions.

Run with:
    python migrations/add_submittal_id_to_notifications.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app import create_app
from app.models import db


def column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(db.engine)
    if table_name not in inspector.get_table_names():
        return False
    return any(c['name'] == column_name for c in inspector.get_columns(table_name))


def migrate() -> bool:
    app = create_app()
    with app.app_context():
        try:
            if column_exists('notifications', 'submittal_id'):
                print("✓ Column 'notifications.submittal_id' already exists. Skipping.")
                return True

            print("Adding submittal_id column to notifications table...")
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE notifications "
                    "ADD COLUMN submittal_id VARCHAR(255) "
                    "REFERENCES submittals(submittal_id) ON DELETE CASCADE"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_notifications_submittal_id "
                    "ON notifications (submittal_id)"
                ))

            if column_exists('notifications', 'submittal_id'):
                print("✓ Successfully added 'submittal_id' column")
                return True
            print("✗ ERROR: Column was not created")
            return False
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
