"""
Script to fix desynced cards by restoring missing trello_list_name and trello_list_id fields.

This script:
- Finds all jobs with trello_card_id but missing trello_list_id or trello_list_name
- Fetches each card from Trello API to get current list information
- Updates the database with the missing list ID and name

Usage:
    python fix_missing_trello_list_info.py          # Run update
    python fix_missing_trello_list_info.py scan    # Preview without updating
"""

import sys
from sqlalchemy import or_
from app.config import Config as cfg
from app.models import Job, db
from app import create_app
from app.trello.api import get_trello_card_by_id, get_list_name_by_id


def scan_missing_list_info(return_json=False):
    """
    Scan and preview which cards would be updated without actually updating them.
    
    Args:
        return_json: If True, returns a dictionary instead of printing
    
    Returns:
        dict with scan results if return_json=True, None otherwise
    """
    if not return_json:
        print("=" * 60)
        print("Scanning for missing Trello list information (PREVIEW MODE)")
        print("=" * 60)
    
    # Get all jobs with trello_card_id but missing list info
    if not return_json:
        print("\n[STEP 1] Fetching jobs from database...")
    
    jobs = Job.query.filter(
        Job.trello_card_id.isnot(None),
        or_(
            Job.trello_list_id.is_(None),
            Job.trello_list_name.is_(None)
        )
    ).all()
    
    if not return_json:
        print(f"[INFO] Found {len(jobs)} job(s) with Trello cards but missing list info")
    
    if len(jobs) == 0:
        if return_json:
            return {"message": "No jobs need fixing", "total_jobs": 0}
        print("[INFO] No jobs need fixing - all cards have list information")
        return
    
    # Scan each job
    if not return_json:
        print("\n[STEP 2] Scanning Trello cards...")
    
    would_fix_count = 0
    not_found_count = 0
    error_count = 0
    sample_fixes = []
    
    for job in jobs:
        job_id = f"{job.job}-{job.release}"
        
        # Fetch card from Trello
        try:
            card_data = get_trello_card_by_id(job.trello_card_id)
            
            if not card_data:
                not_found_count += 1
                if not return_json:
                    print(f"[WARN] Job {job_id}: Card {job.trello_card_id} not found in Trello")
                continue
            
            # Get list ID from card
            list_id = card_data.get("idList")
            if not list_id:
                error_count += 1
                if not return_json:
                    print(f"[WARN] Job {job_id}: Card has no list ID in Trello response")
                continue
            
            # Get list name
            list_name = get_list_name_by_id(list_id)
            if not list_name:
                error_count += 1
                if not return_json:
                    print(f"[WARN] Job {job_id}: Could not get list name for list ID {list_id}")
                continue
            
            # Collect sample for preview
            if len(sample_fixes) < 10:
                sample_fixes.append({
                    "job_id": job_id,
                    "card_id": job.trello_card_id[:8] + "...",
                    "current_list_id": job.trello_list_id or "None",
                    "current_list_name": job.trello_list_name or "None",
                    "new_list_id": list_id,
                    "new_list_name": list_name
                })
            
            would_fix_count += 1
            
        except Exception as e:
            error_count += 1
            if not return_json:
                print(f"[ERROR] Job {job_id}: Error fetching card: {e}")
            continue
    
    # Build result
    result = {
        "total_needs_fixing": len(jobs),
        "would_fix": would_fix_count,
        "not_found_in_trello": not_found_count,
        "errors": error_count,
        "sample_fixes": sample_fixes
    }
    
    if return_json:
        return result
    
    # Summary
    print("\n" + "=" * 60)
    print("Scan Summary (PREVIEW - No Updates Made)")
    print("=" * 60)
    print(f"Jobs needing fix: {len(jobs)}")
    print(f"Would fix: {would_fix_count}")
    print(f"Not found in Trello: {not_found_count}")
    print(f"Errors: {error_count}")
    
    if sample_fixes:
        print(f"\nSample of cards that would be fixed (showing first 10):")
        for sample in sample_fixes:
            print(f"  - {sample['job_id']} (Card: {sample['card_id']})")
            print(f"    Current: list_id={sample['current_list_id']}, list_name={sample['current_list_name']}")
            print(f"    New:     list_id={sample['new_list_id']}, list_name={sample['new_list_name']}")
    
    print("\n" + "=" * 60)
    print("To perform the actual update, run without 'scan' argument")
    print("=" * 60)


def fix_missing_list_info(return_json=False):
    """
    Main function to fix all cards with missing Trello list information.
    
    Args:
        return_json: If True, returns a dictionary instead of printing
    
    Returns:
        dict with fix results if return_json=True, None otherwise
    """
    if not return_json:
        print("=" * 60)
        print("Starting fix for missing Trello list information")
        print("=" * 60)
    
    # Get all jobs with trello_card_id but missing list info
    if not return_json:
        print("\n[STEP 1] Fetching jobs from database...")
    jobs = Job.query.filter(
        Job.trello_card_id.isnot(None),
        or_(
            Job.trello_list_id.is_(None),
            Job.trello_list_name.is_(None)
        )
    ).all()
    if not return_json:
        print(f"[INFO] Found {len(jobs)} job(s) with Trello cards but missing list info")
    
    if len(jobs) == 0:
        if return_json:
            return {"message": "No jobs need fixing", "total_jobs": 0}
        print("[INFO] No jobs need fixing - all cards have list information")
        return
    
    # Process each job
    if not return_json:
        print("\n[STEP 2] Fixing Trello list information...")
    fixed_count = 0
    not_found_count = 0
    error_count = 0
    skipped_count = 0
    fixed_jobs = []
    
    for job in jobs:
        job_id = f"{job.job}-{job.release}"
        
        # Fetch card from Trello
        try:
            card_data = get_trello_card_by_id(job.trello_card_id)
            
            if not card_data:
                if not return_json:
                    print(f"[WARN] Job {job_id}: Card {job.trello_card_id} not found in Trello")
                not_found_count += 1
                continue
            
            # Get list ID from card
            list_id = card_data.get("idList")
            if not list_id:
                if not return_json:
                    print(f"[WARN] Job {job_id}: Card has no list ID in Trello response")
                error_count += 1
                continue
            
            # Get list name
            list_name = get_list_name_by_id(list_id)
            if not list_name:
                if not return_json:
                    print(f"[WARN] Job {job_id}: Could not get list name for list ID {list_id}")
                error_count += 1
                continue
            
            # Check if update is needed
            needs_update = False
            if job.trello_list_id != list_id:
                needs_update = True
                if not return_json:
                    print(f"[INFO] Job {job_id}: Updating list_id from '{job.trello_list_id}' to '{list_id}'")
            
            if job.trello_list_name != list_name:
                needs_update = True
                if not return_json:
                    print(f"[INFO] Job {job_id}: Updating list_name from '{job.trello_list_name}' to '{list_name}'")
            
            if not needs_update:
                skipped_count += 1
                continue
            
            # Update the record
            job.trello_list_id = list_id
            job.trello_list_name = list_name
            db.session.add(job)
            
            if not return_json:
                print(f"[SUCCESS] Job {job_id}: Fixed list info - now in list '{list_name}' ({list_id})")
            fixed_count += 1
            fixed_jobs.append({
                "job_id": job_id,
                "card_id": job.trello_card_id[:8] + "...",
                "list_id": list_id,
                "list_name": list_name
            })
            
        except Exception as e:
            if not return_json:
                print(f"[ERROR] Job {job_id}: Error fixing card: {e}")
            error_count += 1
            continue
    
    # Commit all changes
    if fixed_count > 0:
        try:
            db.session.commit()
            if not return_json:
                print(f"\n[SUCCESS] Committed {fixed_count} updates to database")
        except Exception as e:
            if not return_json:
                print(f"\n[ERROR] Failed to commit changes: {e}")
            db.session.rollback()
            error_count += fixed_count
            fixed_count = 0
    
    # Build result
    result = {
        "total_needing_fix": len(jobs),
        "fixed": fixed_count,
        "skipped": skipped_count,
        "not_found_in_trello": not_found_count,
        "errors": error_count,
        "fixed_jobs": fixed_jobs[:10]  # Limit to first 10 for response size
    }
    
    if return_json:
        return result
    
    # Summary
    print("\n" + "=" * 60)
    print("Fix Summary")
    print("=" * 60)
    print(f"Jobs needing fix: {len(jobs)}")
    print(f"Successfully fixed: {fixed_count}")
    print(f"Skipped (already correct): {skipped_count}")
    print(f"Not found in Trello: {not_found_count}")
    print(f"Errors: {error_count}")
    print("=" * 60)


if __name__ == "__main__":
    app = create_app()
    
    with app.app_context():
        # Check for scan mode
        if len(sys.argv) > 1 and sys.argv[1].lower() == "scan":
            scan_missing_list_info()
        else:
            fix_missing_list_info()

