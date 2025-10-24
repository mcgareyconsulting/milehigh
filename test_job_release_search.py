#!/usr/bin/env python3
"""
Test script to demonstrate job-release search functionality.

This script shows how to search for job changes using job-release
identifiers instead of internal database IDs.
"""

import os
import sys
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, Job, JobChange
from app.change_tracker import (
    get_job_changes_by_release, 
    get_job_change_summary_by_release,
    get_field_change_history_by_release
)

def test_job_release_search():
    """Test the job-release search functionality."""
    app = create_app()
    
    with app.app_context():
        print("🔍 Testing Job-Release Search Functionality")
        print("=" * 50)
        
        # Get a sample job
        job = Job.query.first()
        if not job:
            print("❌ No jobs found in database")
            return
        
        job_release = f"{job.job}-{job.release}"
        print(f"📋 Testing with Job-Release: {job_release}")
        print(f"   Job Name: {job.job_name}")
        print(f"   Internal Job ID: {job.id}")
        print()
        
        # Test 1: Search changes by job-release
        print("1️⃣ Testing search by job-release...")
        try:
            changes = get_job_changes_by_release(job_release=job_release, limit=10)
            print(f"   ✅ Found {len(changes)} changes for job-release {job_release}")
            for change in changes[:3]:  # Show first 3
                print(f"      - {change.field_name}: {change.old_value} → {change.new_value} ({change.source_system})")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 2: Get change summary by job-release
        print("\n2️⃣ Testing change summary by job-release...")
        try:
            summary = get_job_change_summary_by_release(job_release)
            print(f"   ✅ Summary for job-release {job_release}:")
            print(f"      - Total changes: {summary['total_changes']}")
            print(f"      - Fields changed: {', '.join(summary['fields_changed'])}")
            print(f"      - Changes by source: {summary['changes_by_source']}")
            print(f"      - First change: {summary['first_change']}")
            print(f"      - Last change: {summary['last_change']}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 3: Search by field and job-release
        print("\n3️⃣ Testing field-specific search by job-release...")
        try:
            field_changes = get_field_change_history_by_release(job_release, "notes", limit=5)
            print(f"   ✅ Found {len(field_changes)} changes for 'notes' field in {job_release}")
            for change in field_changes:
                print(f"      - {change.changed_at}: {change.old_value} → {change.new_value}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 4: Search with filters
        print("\n4️⃣ Testing filtered search by job-release...")
        try:
            # Search for changes in the last hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_changes = get_job_changes_by_release(
                job_release=job_release,
                start_date=one_hour_ago,
                limit=5
            )
            print(f"   ✅ Found {len(recent_changes)} changes in last hour for {job_release}")
            
            # Search by source system
            trello_changes = get_job_changes_by_release(
                job_release=job_release,
                source_system="Trello",
                limit=5
            )
            print(f"   ✅ Found {len(trello_changes)} Trello changes for {job_release}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 5: Test with a non-existent job-release
        print("\n5️⃣ Testing with non-existent job-release...")
        try:
            fake_job_release = "999-999"
            changes = get_job_changes_by_release(job_release=fake_job_release, limit=5)
            print(f"   ✅ Found {len(changes)} changes for non-existent job-release {fake_job_release}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        print("\n" + "=" * 50)
        print("🎉 Job-release search test completed!")
        print("\n📊 Available API endpoints for job-release search:")
        print("   - GET /jobs/{job_release}/changes - Get job change history")
        print("   - GET /jobs/{job_release}/changes/summary - Get change summary")
        print("   - GET /jobs/{job_release}/changes/field/{field_name} - Get field history")
        print("   - GET /jobs/{job_release}/changes/view - HTML view")
        print("\n💡 Example usage:")
        print(f"   curl 'http://localhost:5000/jobs/{job_release}/changes'")
        print(f"   curl 'http://localhost:5000/jobs/{job_release}/changes/summary'")
        print(f"   curl 'http://localhost:5000/jobs/{job_release}/changes/field/notes'")

if __name__ == "__main__":
    test_job_release_search()
