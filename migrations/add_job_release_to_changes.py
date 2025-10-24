#!/usr/bin/env python3
"""
Migration script to add job-release fields to job_changes table.

This script adds job, release, and job_release columns to the existing
job_changes table and populates them with data from the jobs table.

Run this script from the project root:
    python migrations/add_job_release_to_changes.py
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, JobChange, Job
from sqlalchemy import text

def run_migration():
    """Run the migration to add job-release fields to job_changes table."""
    app = create_app()
    
    with app.app_context():
        try:
            print(f"[{datetime.now()}] Starting migration: Add job-release fields to job_changes")
            
            # Check if columns already exist
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('job_changes')]
            
            if 'job_release' in columns:
                print(f"[{datetime.now()}] Job-release fields already exist. Skipping migration.")
                return True
            
            # Add new columns
            print(f"[{datetime.now()}] Adding job-release columns...")
            
            # Add job column
            db.session.execute(text("ALTER TABLE job_changes ADD COLUMN job INTEGER"))
            print(f"[{datetime.now()}] Added 'job' column")
            
            # Add release column
            db.session.execute(text("ALTER TABLE job_changes ADD COLUMN release VARCHAR(16)"))
            print(f"[{datetime.now()}] Added 'release' column")
            
            # Add job_release column
            db.session.execute(text("ALTER TABLE job_changes ADD COLUMN job_release VARCHAR(32)"))
            print(f"[{datetime.now()}] Added 'job_release' column")
            
            # Create indexes
            print(f"[{datetime.now()}] Creating indexes...")
            db.session.execute(text("CREATE INDEX ix_job_changes_job ON job_changes (job)"))
            db.session.execute(text("CREATE INDEX ix_job_changes_release ON job_changes (release)"))
            db.session.execute(text("CREATE INDEX ix_job_changes_job_release ON job_changes (job_release)"))
            print(f"[{datetime.now()}] Created indexes")
            
            # Populate the new columns with data from jobs table
            print(f"[{datetime.now()}] Populating job-release data...")
            
            # Update existing records
            update_query = text("""
                UPDATE job_changes 
                SET job = j.job, 
                    release = j.release, 
                    job_release = j.job || '-' || j.release
                FROM jobs j 
                WHERE job_changes.job_id = j.id
            """)
            
            result = db.session.execute(update_query)
            updated_count = result.rowcount
            print(f"[{datetime.now()}] Updated {updated_count} existing records")
            
            # For SQLite, we can't easily make columns NOT NULL after creation
            # The columns will be nullable but we'll handle this in the application layer
            print(f"[{datetime.now()}] Note: Columns are nullable (SQLite limitation)")
            
            # Commit all changes
            db.session.commit()
            
            print(f"[{datetime.now()}] ✅ Successfully added job-release fields to job_changes table")
            
            # Verify the migration
            inspector = db.inspect(db.engine)
            columns_after = [col['name'] for col in inspector.get_columns('job_changes')]
            
            required_columns = ['job', 'release', 'job_release']
            if all(col in columns_after for col in required_columns):
                print(f"[{datetime.now()}] ✅ Migration verification successful")
                
                # Show sample data
                sample = db.session.execute(text("SELECT job, release, job_release FROM job_changes LIMIT 5")).fetchall()
                print(f"[{datetime.now()}] Sample data:")
                for row in sample:
                    print(f"  - Job: {row[0]}, Release: {row[1]}, Job-Release: {row[2]}")
                
                return True
            else:
                print(f"[{datetime.now()}] ❌ Migration verification failed")
                return False
                
        except Exception as e:
            print(f"[{datetime.now()}] ❌ Migration failed: {str(e)}")
            db.session.rollback()
            return False

def rollback_migration():
    """Rollback the migration by removing the job-release columns."""
    app = create_app()
    
    with app.app_context():
        try:
            print(f"[{datetime.now()}] Rolling back migration: Remove job-release fields from job_changes")
            
            # Check if columns exist
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('job_changes')]
            
            if 'job_release' not in columns:
                print(f"[{datetime.now()}] Job-release fields do not exist. Nothing to rollback.")
                return True
            
            # Drop indexes first
            print(f"[{datetime.now()}] Dropping indexes...")
            try:
                db.session.execute(text("DROP INDEX IF EXISTS ix_job_changes_job"))
                db.session.execute(text("DROP INDEX IF EXISTS ix_job_changes_release"))
                db.session.execute(text("DROP INDEX IF EXISTS ix_job_changes_job_release"))
            except Exception as e:
                print(f"[{datetime.now()}] Warning: Could not drop indexes: {e}")
            
            # Drop columns
            print(f"[{datetime.now()}] Dropping columns...")
            db.session.execute(text("ALTER TABLE job_changes DROP COLUMN IF EXISTS job_release"))
            db.session.execute(text("ALTER TABLE job_changes DROP COLUMN IF EXISTS release"))
            db.session.execute(text("ALTER TABLE job_changes DROP COLUMN IF EXISTS job"))
            
            db.session.commit()
            
            print(f"[{datetime.now()}] ✅ Successfully removed job-release fields from job_changes table")
            return True
            
        except Exception as e:
            print(f"[{datetime.now()}] ❌ Rollback failed: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migration script for job-release fields in job_changes table")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    
    args = parser.parse_args()
    
    if args.rollback:
        success = rollback_migration()
    else:
        success = run_migration()
    
    sys.exit(0 if success else 1)
