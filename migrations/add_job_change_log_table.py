"""
Migration script to add the JobChangeLog table.

This migration adds the job_change_logs table to track state changes and field updates
for jobs over time.

Run this script with:
    python migrations/add_job_change_log_table.py

Or from the app context:
    from migrations.add_job_change_log_table import migrate
    migrate()
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, JobChangeLog
from sqlalchemy import inspect


def table_exists(table_name):
    """Check if a table exists in the database."""
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()


def migrate():
    """Create the job_change_logs table if it doesn't exist."""
    app = create_app()
    
    with app.app_context():
        # Check if table already exists
        if table_exists('job_change_logs'):
            print("✓ Table 'job_change_logs' already exists. Migration not needed.")
            return
        
        print("Creating 'job_change_logs' table...")
        
        try:
            # Create the table
            JobChangeLog.__table__.create(db.engine, checkfirst=True)
            print("✓ Successfully created 'job_change_logs' table")
            
            # Verify the table was created
            if table_exists('job_change_logs'):
                print("✓ Verification: Table 'job_change_logs' exists")
                
                # Show table structure
                inspector = inspect(db.engine)
                columns = inspector.get_columns('job_change_logs')
                print("\nTable structure:")
                for col in columns:
                    print(f"  - {col['name']}: {col['type']}")
                
                # Show indexes
                indexes = inspector.get_indexes('job_change_logs')
                if indexes:
                    print("\nIndexes:")
                    for idx in indexes:
                        print(f"  - {idx['name']}: {idx['column_names']}")
                
            else:
                print("✗ ERROR: Table creation verification failed")
                return False
                
        except Exception as e:
            print(f"✗ ERROR: Failed to create table: {e}")
            db.session.rollback()
            return False
        
        return True


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)

