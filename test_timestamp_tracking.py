#!/usr/bin/env python3
"""
Test script to demonstrate timestamp tracking functionality.

This script shows how to use the new timestamp tracking features
to monitor job changes and query change history.
"""

import os
import sys
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, Job, JobChange
from app.change_tracker import (
    track_job_change, 
    track_multiple_changes, 
    get_job_changes, 
    get_job_change_summary,
    get_field_change_history,
    get_recent_changes
)

def test_timestamp_tracking():
    """Test the timestamp tracking functionality."""
    app = create_app()
    
    with app.app_context():
        print("🔍 Testing Timestamp Tracking System")
        print("=" * 50)
        
        # Get a sample job
        job = Job.query.first()
        if not job:
            print("❌ No jobs found in database")
            return
        
        print(f"📋 Testing with Job: {job.job}-{job.release} - {job.job_name}")
        print(f"   Job ID: {job.id}")
        print()
        
        # Test 1: Track a single change
        print("1️⃣ Testing single change tracking...")
        try:
            change = track_job_change(
                job_id=job.id,
                field_name="notes",
                old_value=job.notes,
                new_value="Test note from timestamp tracking demo",
                source_system="system",
                operation_id="test-001",
                change_type="update",
                user_context="Test script",
                metadata={"test": True, "demo": "timestamp_tracking"}
            )
            print(f"   ✅ Created change record: {change.id}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 2: Track multiple changes
        print("\n2️⃣ Testing multiple changes tracking...")
        try:
            changes = track_multiple_changes(
                job_id=job.id,
                changes=[
                    {
                        'field_name': 'description',
                        'old_value': job.description,
                        'new_value': f"Updated description at {datetime.now()}",
                        'change_type': 'update'
                    },
                    {
                        'field_name': 'pm',
                        'old_value': job.pm,
                        'new_value': 'TEST_PM',
                        'change_type': 'update'
                    }
                ],
                source_system="system",
                operation_id="test-002",
                user_context="Test script - multiple changes",
                metadata={"test": True, "batch": True}
            )
            print(f"   ✅ Created {len(changes)} change records")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 3: Query job changes
        print("\n3️⃣ Testing job changes query...")
        try:
            changes = get_job_changes(job_id=job.id, limit=10)
            print(f"   ✅ Found {len(changes)} changes for job {job.id}")
            for change in changes[:3]:  # Show first 3
                print(f"      - {change.field_name}: {change.old_value} → {change.new_value} ({change.source_system})")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 4: Get change summary
        print("\n4️⃣ Testing change summary...")
        try:
            summary = get_job_change_summary(job.id)
            print(f"   ✅ Summary for job {job.id}:")
            print(f"      - Total changes: {summary['total_changes']}")
            print(f"      - Fields changed: {', '.join(summary['fields_changed'])}")
            print(f"      - Changes by source: {summary['changes_by_source']}")
            print(f"      - First change: {summary['first_change']}")
            print(f"      - Last change: {summary['last_change']}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 5: Get field change history
        print("\n5️⃣ Testing field change history...")
        try:
            field_changes = get_field_change_history(job.id, "notes", limit=5)
            print(f"   ✅ Found {len(field_changes)} changes for 'notes' field")
            for change in field_changes:
                print(f"      - {change.changed_at}: {change.old_value} → {change.new_value}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Test 6: Get recent changes
        print("\n6️⃣ Testing recent changes query...")
        try:
            recent = get_recent_changes(hours=1, limit=5)
            print(f"   ✅ Found {len(recent)} recent changes in last hour")
            for change in recent[:3]:  # Show first 3
                print(f"      - Job {change.job_id}: {change.field_name} ({change.source_system})")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        print("\n" + "=" * 50)
        print("🎉 Timestamp tracking test completed!")
        print("\n📊 Available API endpoints:")
        print("   - GET /jobs/{job_id}/changes - Get job change history")
        print("   - GET /jobs/{job_id}/changes/summary - Get change summary")
        print("   - GET /jobs/{job_id}/changes/field/{field_name} - Get field history")
        print("   - GET /changes/recent - Get recent changes")
        print("   - GET /changes/stats - Get change statistics")
        print("   - GET /jobs/{job_id}/changes/view - HTML view")
        print("   - GET /changes/recent/view - HTML view")

if __name__ == "__main__":
    test_timestamp_tracking()
