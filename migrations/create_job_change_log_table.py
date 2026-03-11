"""
Migration script to create the JobChangeLog table.

Run this script with:
    python migrations/create_job_change_log_table.py

This table tracks state changes and field updates for jobs over time.
Records are created when Job fields change via OneDrive sync or Trello updates.
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, JobChangeLog


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()


def migrate() -> bool:
    """
    Create the JobChangeLog table if it doesn't exist.

    Returns:
        bool: True if migration was successful or already completed, False on error.
    """
    app = create_app()
    with app.app_context():
        try:
            if table_exists('job_change_logs'):
                print("✓ Table 'job_change_logs' already exists. Skipping creation.")
                return True

            print("Creating 'job_change_logs' table...")
            db.create_all()

            # Verify creation
            if table_exists('job_change_logs'):
                print("✓ Successfully created 'job_change_logs' table")
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
