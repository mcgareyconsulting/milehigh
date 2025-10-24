#!/usr/bin/env python3
"""
Create test changes to demonstrate job-release search functionality.
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, Job, JobChange
from app.change_tracker import track_multiple_changes

def create_test_changes():
    """Create some test changes to demonstrate the functionality."""
    app = create_app()
    
    with app.app_context():
        print("🔧 Creating test changes for job-release search demo")
        print("=" * 50)
        
        # Get a sample job
        job = Job.query.first()
        if not job:
            print("❌ No jobs found in database")
            return
        
        job_release = f"{job.job}-{job.release}"
        print(f"📋 Creating test changes for: {job_release} - {job.job_name}")
        
        # Create some test changes
        test_changes = [
            {
                'field_name': 'notes',
                'old_value': job.notes,
                'new_value': f"Test note updated at {datetime.now()}",
                'change_type': 'update'
            },
            {
                'field_name': 'description',
                'old_value': job.description,
                'new_value': f"Updated description for testing job-release search",
                'change_type': 'update'
            },
            {
                'field_name': 'pm',
                'old_value': job.pm,
                'new_value': 'TEST_PM',
                'change_type': 'update'
            }
        ]
        
        try:
            changes = track_multiple_changes(
                job_id=job.id,
                changes=test_changes,
                source_system="system",
                operation_id="test-job-release-search",
                user_context="Test script for job-release search demo",
                metadata={"test": True, "demo": "job_release_search"},
                job=job.job,
                release=job.release
            )
            
            print(f"✅ Created {len(changes)} test changes")
            for change in changes:
                print(f"   - {change.field_name}: {change.old_value} → {change.new_value}")
            
            print(f"\n🎯 Now you can test job-release search with:")
            print(f"   curl 'http://localhost:5000/jobs/{job_release}/changes'")
            print(f"   curl 'http://localhost:5000/jobs/{job_release}/changes/summary'")
            print(f"   http://localhost:5000/jobs/{job_release}/changes/view")
            
        except Exception as e:
            print(f"❌ Error creating test changes: {e}")

if __name__ == "__main__":
    create_test_changes()
