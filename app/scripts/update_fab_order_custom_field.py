"""
Script to update existing Trello cards with the 'Fab Order' custom field
based on the fab_order value from the database.

This script:
- Finds all jobs with trello_card_id in "Released" or "Fit Up Complete" lists
- Gets the 'Fab Order' custom field ID from the Trello board
- Updates each card's custom field with the db fab_order value
- Ignores null values
- Rounds up float values to int

Usage:
    python update_fab_order_custom_field.py          # Run update
    python update_fab_order_custom_field.py scan    # Preview without updating
"""

import math
import sys
from app.config import Config as cfg
from app.models import Job, db
from app import create_app
from app.trello.api import (
    get_board_custom_fields,
    find_fab_order_field_id,
    update_card_custom_field_number
)


def scan_fab_order_updates(return_json=False):
    """
    Scan and preview how many cards would be updated without actually updating them.
    
    Args:
        return_json: If True, returns a dictionary instead of printing
    
    Returns:
        dict with scan results if return_json=True, None otherwise
    """
    if not return_json:
        print("=" * 60)
        print("Scanning Fab Order custom field updates (PREVIEW MODE)")
        print("=" * 60)
    
    # Get custom fields from board
    if not return_json:
        print("\n[STEP 1] Fetching custom fields from Trello board...")
    custom_fields = get_board_custom_fields(cfg.TRELLO_BOARD_ID)
    
    if not custom_fields:
        error_msg = "Failed to retrieve custom fields from Trello board"
        if return_json:
            return {"error": error_msg}
        print(f"[ERROR] {error_msg}")
        return
    
    if not return_json:
        print(f"[INFO] Found {len(custom_fields)} custom field(s) on board")
    
    # Find Fab Order field ID
    if not return_json:
        print("\n[STEP 2] Finding 'Fab Order' custom field...")
    fab_order_field_id = find_fab_order_field_id(custom_fields)
    
    if not fab_order_field_id:
        error_msg = "'Fab Order' custom field not found on the board"
        if return_json:
            available_fields = [{"name": field.get('name'), "id": field.get('id')} for field in custom_fields]
            return {"error": error_msg, "available_fields": available_fields}
        print(f"[ERROR] {error_msg}")
        print("[INFO] Available custom fields:")
        for field in custom_fields:
            print(f"  - {field.get('name')} (ID: {field.get('id')})")
        return
    
    if not return_json:
        print(f"[INFO] Found 'Fab Order' custom field (ID: {fab_order_field_id})")
    
    # Get all jobs with trello_card_id
    if not return_json:
        print("\n[STEP 3] Fetching jobs from database...")
    jobs = Job.query.filter(Job.trello_card_id.isnot(None)).all()
    if not return_json:
        print(f"[INFO] Found {len(jobs)} job(s) with Trello cards")
    
    if len(jobs) == 0:
        if return_json:
            return {"message": "No jobs to process", "total_jobs": 0}
        print("[INFO] No jobs to process")
        return
    
    # Filter jobs to only those in "Released" or "Fit Up Complete" lists
    target_list_ids = [cfg.NEW_TRELLO_CARD_LIST_ID, cfg.FIT_UP_COMPLETE_LIST_ID]
    filtered_jobs = [job for job in jobs if job.trello_list_id in target_list_ids]
    if not return_json:
        print(f"[INFO] Filtered to {len(filtered_jobs)} job(s) in target lists (Released or Fit Up Complete)")
    
    if len(filtered_jobs) == 0:
        if return_json:
            return {
                "message": "No jobs in target lists to process",
                "total_jobs": len(jobs),
                "filtered_jobs": 0
            }
        print("[INFO] No jobs in target lists to process")
        return
    
    # Scan each job
    if not return_json:
        print("\n[STEP 4] Scanning jobs...")
    would_update_count = 0
    skipped_null_count = 0
    error_count = 0
    sample_updates = []
    
    for job in filtered_jobs:
        job_id = f"{job.job}-{job.release}"
        
        # Skip if fab_order is None
        if job.fab_order is None:
            skipped_null_count += 1
            continue
        
        # Convert to int (round up if float)
        try:
            if isinstance(job.fab_order, float):
                fab_order_int = math.ceil(job.fab_order)
            else:
                fab_order_int = int(job.fab_order)
            
            # Collect sample for preview
            if len(sample_updates) < 5:
                sample_updates.append({
                    "job_id": job_id,
                    "card_id": job.trello_card_id[:8] + "...",
                    "list_name": job.trello_list_name or "Unknown",
                    "current_fab_order": job.fab_order,
                    "fab_order_int": fab_order_int
                })
            
            would_update_count += 1
        except (ValueError, TypeError) as e:
            error_count += 1
            continue
    
    # Build result
    result = {
        "total_jobs": len(jobs),
        "filtered_jobs": len(filtered_jobs),
        "would_update": would_update_count,
        "skipped_null_fab_order": skipped_null_count,
        "skipped_not_in_target_lists": len(jobs) - len(filtered_jobs),
        "would_error": error_count,
        "sample_updates": sample_updates
    }
    
    if return_json:
        return result
    
    # Summary
    print("\n" + "=" * 60)
    print("Scan Summary (PREVIEW - No Updates Made)")
    print("=" * 60)
    print(f"Total jobs with Trello cards: {len(jobs)}")
    print(f"Jobs in target lists (Released/Fit Up Complete): {len(filtered_jobs)}")
    print(f"\nWould update: {would_update_count}")
    print(f"Would skip (null fab_order): {skipped_null_count}")
    print(f"Would skip (not in target lists): {len(jobs) - len(filtered_jobs)}")
    print(f"Would error: {error_count}")
    
    if sample_updates:
        print(f"\nSample of cards that would be updated (showing first 5):")
        for sample in sample_updates:
            print(f"  - {sample['job_id']} (Card: {sample['card_id']})")
            print(f"    List: {sample['list_name']}")
            print(f"    Fab Order: {sample['current_fab_order']} -> {sample['fab_order_int']}")
    
    print("\n" + "=" * 60)
    print("To perform the actual update, run without 'scan' argument")
    print("=" * 60)


def process_fab_order_updates():
    """
    Main function to update all Trello cards with Fab Order custom field.
    """
    print("=" * 60)
    print("Starting Fab Order custom field update process")
    print("=" * 60)
    
    # Get custom fields from board
    print("\n[STEP 1] Fetching custom fields from Trello board...")
    custom_fields = get_board_custom_fields(cfg.TRELLO_BOARD_ID)
    
    if not custom_fields:
        print("[ERROR] Failed to retrieve custom fields from Trello board")
        return
    
    print(f"[INFO] Found {len(custom_fields)} custom field(s) on board")
    
    # Find Fab Order field ID
    print("\n[STEP 2] Finding 'Fab Order' custom field...")
    fab_order_field_id = find_fab_order_field_id(custom_fields)
    
    if not fab_order_field_id:
        print("[ERROR] 'Fab Order' custom field not found on the board")
        print("[INFO] Available custom fields:")
        for field in custom_fields:
            print(f"  - {field.get('name')} (ID: {field.get('id')})")
        return
    
    print(f"[INFO] Found 'Fab Order' custom field (ID: {fab_order_field_id})")
    
    # Get all jobs with trello_card_id
    print("\n[STEP 3] Fetching jobs from database...")
    jobs = Job.query.filter(Job.trello_card_id.isnot(None)).all()
    print(f"[INFO] Found {len(jobs)} job(s) with Trello cards")
    
    if len(jobs) == 0:
        print("[INFO] No jobs to process")
        return
    
    # Filter jobs to only those in "Released" or "Fit Up Complete" lists
    target_list_ids = [cfg.NEW_TRELLO_CARD_LIST_ID, cfg.FIT_UP_COMPLETE_LIST_ID]
    filtered_jobs = [job for job in jobs if job.trello_list_id in target_list_ids]
    print(f"[INFO] Filtered to {len(filtered_jobs)} job(s) in target lists (Released or Fit Up Complete)")
    
    if len(filtered_jobs) == 0:
        print("[INFO] No jobs in target lists to process")
        return
    
    # Process each job
    print("\n[STEP 4] Updating Trello cards...")
    updated_count = 0
    skipped_null_count = 0
    error_count = 0
    
    for job in filtered_jobs:
        job_id = f"{job.job}-{job.release}"
        
        # Skip if fab_order is None
        if job.fab_order is None:
            print(f"[SKIP] Job {job_id}: fab_order is null, skipping")
            skipped_null_count += 1
            continue
        
        # Convert to int (round up if float)
        try:
            if isinstance(job.fab_order, float):
                fab_order_int = math.ceil(job.fab_order)
            else:
                fab_order_int = int(job.fab_order)
        except (ValueError, TypeError) as e:
            print(f"[ERROR] Job {job_id}: Could not convert fab_order '{job.fab_order}' to int: {e}")
            error_count += 1
            continue
        
        # Update Trello card
        success = update_card_custom_field_number(
            job.trello_card_id,
            fab_order_field_id,
            fab_order_int
        )
        
        if success:
            print(f"[SUCCESS] Job {job_id}: Updated card {job.trello_card_id} with Fab Order = {fab_order_int}")
            updated_count += 1
        else:
            print(f"[ERROR] Job {job_id}: Failed to update card {job.trello_card_id}")
            error_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("Update Summary")
    print("=" * 60)
    print(f"Total jobs with Trello cards: {len(jobs)}")
    print(f"Jobs in target lists (Released/Fit Up Complete): {len(filtered_jobs)}")
    print(f"Successfully updated: {updated_count}")
    print(f"Skipped (null fab_order): {skipped_null_count}")
    print(f"Skipped (not in target lists): {len(jobs) - len(filtered_jobs)}")
    print(f"Errors: {error_count}")
    print("=" * 60)


if __name__ == "__main__":
    app = create_app()
    
    with app.app_context():
        # Check for scan mode
        if len(sys.argv) > 1 and sys.argv[1].lower() == "scan":
            scan_fab_order_updates()
        else:
            process_fab_order_updates()
