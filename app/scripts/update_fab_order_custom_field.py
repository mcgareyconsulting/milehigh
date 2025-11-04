"""
Script to update existing Trello cards with the 'Fab Order' custom field
based on the fab_order value from the database.

This script:
- Finds all jobs with trello_card_id
- Gets the 'Fab Order' custom field ID from the Trello board
- Updates each card's custom field with the db fab_order value
- Ignores null values
- Rounds up float values to int
"""

import math
from app.config import Config as cfg
from app.models import Job, db
from app import create_app
from app.trello.api import (
    get_board_custom_fields,
    find_fab_order_field_id,
    update_card_custom_field_number
)


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
    
    # Process each job
    print("\n[STEP 4] Updating Trello cards...")
    updated_count = 0
    skipped_null_count = 0
    error_count = 0
    
    for job in jobs:
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
    print(f"Total jobs processed: {len(jobs)}")
    print(f"Successfully updated: {updated_count}")
    print(f"Skipped (null fab_order): {skipped_null_count}")
    print(f"Errors: {error_count}")
    print("=" * 60)


if __name__ == "__main__":
    app = create_app()
    
    with app.app_context():
        process_fab_order_updates()
