#!/usr/bin/env python3
"""
Migration script to add job_changes table for timestamp tracking.

This script adds a new table to track individual field changes to jobs
with timestamps, source system, and change context.

Run this script from the project root:
    python migrations/add_job_changes_table.py
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, JobChange
from sqlalchemy import text

def run_migration():
    """Run the migration to add the job_changes table."""
    app = create_app()
    
    with app.app_context():
        try:
            print(f"[{datetime.now()}] Starting migration: Add job_changes table")
            
            # Check if the table already exists
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if 'job_changes' in existing_tables:
                print(f"[{datetime.now()}] Table 'job_changes' already exists. Skipping migration.")
                return True
            
            # Create the job_changes table
            print(f"[{datetime.now()}] Creating job_changes table...")
            db.create_all()
            
            # Verify the table was created
            inspector = db.inspect(db.engine)
            tables_after = inspector.get_table_names()
            
            if 'job_changes' in tables_after:
                print(f"[{datetime.now()}] ✅ Successfully created job_changes table")
                
                # Show table structure
                columns = inspector.get_columns('job_changes')
                print(f"[{datetime.now()}] Table structure:")
                for col in columns:
                    print(f"  - {col['name']}: {col['type']} {'(nullable)' if col['nullable'] else '(not null)'}")
                
                return True
            else:
                print(f"[{datetime.now()}] ❌ Failed to create job_changes table")
                return False
                
        except Exception as e:
            print(f"[{datetime.now()}] ❌ Migration failed: {str(e)}")
            return False

def rollback_migration():
    """Rollback the migration by dropping the job_changes table."""
    app = create_app()
    
    with app.app_context():
        try:
            print(f"[{datetime.now()}] Rolling back migration: Drop job_changes table")
            
            # Check if the table exists
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if 'job_changes' not in existing_tables:
                print(f"[{datetime.now()}] Table 'job_changes' does not exist. Nothing to rollback.")
                return True
            
            # Drop the table
            print(f"[{datetime.now()}] Dropping job_changes table...")
            db.session.execute(text("DROP TABLE job_changes"))
            db.session.commit()
            
            print(f"[{datetime.now()}] ✅ Successfully dropped job_changes table")
            return True
            
        except Exception as e:
            print(f"[{datetime.now()}] ❌ Rollback failed: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migration script for job_changes table")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    
    args = parser.parse_args()
    
    if args.rollback:
        success = rollback_migration()
    else:
        success = run_migration()
    
    sys.exit(0 if success else 1)
