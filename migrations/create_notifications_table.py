"""
Migration script to create the notifications table.

Run this script with:
    python migrations/create_notifications_table.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Notification


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()


def migrate() -> bool:
    """Create notifications table if it doesn't exist."""
    app = create_app()
    with app.app_context():
        try:
            if table_exists('notifications'):
                print("✓ Table 'notifications' already exists. Skipping.")
                return True

            print("Creating notifications table...")
            db.create_all()

            if table_exists('notifications'):
                print("✓ Successfully created 'notifications' table")
                return True
            else:
                print("✗ ERROR: Table was not created")
                return False
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
