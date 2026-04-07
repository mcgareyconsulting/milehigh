"""
Migration script to create the Board tables (board_items and board_activity).

Run this script with:
    python migrations/create_board_tables.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, BoardItem, BoardActivity


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()


def migrate() -> bool:
    """Create board_items and board_activity tables if they don't exist."""
    app = create_app()
    with app.app_context():
        try:
            items_exists = table_exists('board_items')
            activity_exists = table_exists('board_activity')

            if items_exists and activity_exists:
                print("✓ Tables 'board_items' and 'board_activity' already exist. Skipping.")
                return True

            print("Creating board tables...")
            db.create_all()

            if table_exists('board_items') and table_exists('board_activity'):
                print("✓ Successfully created 'board_items' and 'board_activity' tables")
                return True
            else:
                print("✗ ERROR: Tables were not created")
                return False
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
