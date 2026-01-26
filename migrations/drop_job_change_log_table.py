"""
Migration script to drop the deprecated job_change_logs table.

Run this script with:
    python migrations/drop_job_change_log_table.py

Or from the app context:
    from migrations.drop_job_change_log_table import migrate
    migrate()
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db
from sqlalchemy import inspect, MetaData, Table


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()


def migrate() -> bool:
    """
    Drop the job_change_logs table if it exists.
    
    Returns:
        bool: True if migration was successful or already completed, False on error.
    """
    app = create_app()
    with app.app_context():
        try:
            if not table_exists('job_change_logs'):
                print("✓ Table 'job_change_logs' does not exist. Nothing to drop.")
                return True
            
            print("Dropping 'job_change_logs' table...")
            metadata = MetaData()
            metadata.reflect(bind=db.engine, only=['job_change_logs'])
            table = Table('job_change_logs', metadata, autoload_with=db.engine)
            table.drop(bind=db.engine, checkfirst=True)
            
            # Verify drop
            if not table_exists('job_change_logs'):
                print("✓ Successfully dropped 'job_change_logs' table")
                return True
            else:
                print("✗ ERROR: Table still exists after drop attempt")
                return False
        except Exception as e:
            print(f"✗ ERROR: {e}")
            return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)



