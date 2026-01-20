"""
Rebuild Trello data for all jobs by syncing from Trello cards.

This script:
- Fetches all Trello cards from the board
- Extracts job identifiers from card names
- Matches cards to jobs in the database
- Updates job records with Trello card data

This is useful after clearing Trello data or when switching to a new board
where cards already exist.

Usage:
    python -m app.scripts.rebuild_trello_data          # Preview only (dry run)
    python -m app.scripts.rebuild_trello_data --execute  # Actually rebuild the data
"""

import argparse
from app.models import Job, db
from app.trello.api import get_all_trello_cards, update_job_record_with_trello_data, get_list_name_by_id
from app.trello.utils import extract_identifier
from app.logging_config import get_logger

logger = get_logger(__name__)


def rebuild_trello_data(execute=False):
    """
    Rebuild Trello data for all jobs by syncing from Trello cards.
    
    Args:
        execute: If True, actually update the database (default: False for safety)
    
    Returns:
        dict with rebuild results
    """
    print("=" * 80)
    print("REBUILD TRELLO DATA FROM TRELLO CARDS")
    print("=" * 80)
    mode = "DRY RUN (Preview Only)" if not execute else "LIVE MODE - WILL UPDATE DATABASE"
    print(f"\n[INFO] Mode: {mode}")
    
    if not execute:
        print("[WARNING] This is a dry run. Use --execute to actually update the database.")
    
    try:
        # Step 1: Fetch all Trello cards
        print("\n[STEP 1] Fetching all Trello cards from board...")
        
        trello_cards = get_all_trello_cards()
        print(f"[INFO] Found {len(trello_cards)} Trello cards")
        
        if len(trello_cards) == 0:
            print("[INFO] No Trello cards found. Nothing to rebuild.")
            return {
                "total_cards": 0,
                "matched": 0,
                "unmatched": 0,
                "updated": 0,
                "executed": execute
            }
        
        # Step 2: Extract identifiers and match to jobs
        print("\n[STEP 2] Matching Trello cards to database jobs...")
        
        matched_cards = []
        unmatched_cards = []
        
        for card in trello_cards:
            card_name = card.get("name", "").strip()
            if not card_name:
                continue
            
            # Extract identifier from card name
            identifier = extract_identifier(card_name)
            if not identifier:
                unmatched_cards.append({
                    "card_id": card.get("id"),
                    "card_name": card_name,
                    "reason": "Could not extract identifier"
                })
                continue
            
            # Parse identifier to job and release
            parts = identifier.split("-")
            if len(parts) != 2:
                unmatched_cards.append({
                    "card_id": card.get("id"),
                    "card_name": card_name,
                    "identifier": identifier,
                    "reason": "Invalid identifier format"
                })
                continue
            
            try:
                job_number = int(parts[0])
                release_number = parts[1]
            except (ValueError, TypeError):
                unmatched_cards.append({
                    "card_id": card.get("id"),
                    "card_name": card_name,
                    "identifier": identifier,
                    "reason": "Invalid job number"
                })
                continue
            
            # Find matching job in database
            job = Job.query.filter_by(job=job_number, release=release_number).first()
            if not job:
                unmatched_cards.append({
                    "card_id": card.get("id"),
                    "card_name": card_name,
                    "identifier": identifier,
                    "reason": "Job not found in database"
                })
                continue
            
            # Check if job already has Trello data
            has_existing_data = job.trello_card_id is not None
            
            matched_cards.append({
                "card": card,
                "job": job,
                "identifier": identifier,
                "has_existing_data": has_existing_data
            })
        
        print(f"[INFO] Matched {len(matched_cards)} cards to jobs")
        print(f"[INFO] Unmatched {len(unmatched_cards)} cards")
        
        # Step 3: Show sample of what will be updated
        if matched_cards:
            print(f"\n[STEP 3] Sample of jobs that will be updated:")
            for item in matched_cards[:10]:  # Show first 10
                status = "UPDATE" if item["has_existing_data"] else "ADD"
                print(f"  - {item['identifier']}: {status} Trello data")
                print(f"      Card: {item['card'].get('name', '')[:60]}")
                print(f"      List: {item['card'].get('list_name', 'N/A')}")
            if len(matched_cards) > 10:
                print(f"  ... and {len(matched_cards) - 10} more")
        
        if unmatched_cards:
            print(f"\n[INFO] Sample of unmatched cards:")
            for item in unmatched_cards[:5]:  # Show first 5
                print(f"  - {item.get('card_name', 'Unknown')[:60]}: {item.get('reason', 'Unknown')}")
            if len(unmatched_cards) > 5:
                print(f"  ... and {len(unmatched_cards) - 5} more")
        
        # Step 4: Update database
        updated = []
        failed = []
        
        if execute:
            print(f"\n[STEP 4] Updating database for {len(matched_cards)} jobs...")
            
            for idx, item in enumerate(matched_cards, 1):
                card = item["card"]
                job = item["job"]
                identifier = item["identifier"]
                
                try:
                    # Convert card format to match what update_job_record_with_trello_data expects
                    # get_all_trello_cards returns list_id, but update_job_record_with_trello_data expects idList
                    card_data = {
                        "id": card.get("id"),
                        "name": card.get("name"),
                        "desc": card.get("desc", ""),
                        "idList": card.get("list_id")  # Convert list_id to idList
                    }
                    
                    # Update job record with Trello card data
                    success = update_job_record_with_trello_data(job, card_data)
                    
                    if success:
                        updated.append({
                            "identifier": identifier,
                            "card_id": card.get("id"),
                            "card_name": card.get("name"),
                            "list_name": card.get("list_name")
                        })
                        if idx % 10 == 0:
                            print(f"[PROGRESS] Updated {idx}/{len(matched_cards)} jobs...")
                    else:
                        failed.append({
                            "identifier": identifier,
                            "card_id": card.get("id"),
                            "error": "update_job_record_with_trello_data returned False"
                        })
                
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Error updating {identifier}: {error_msg}", exc_info=True)
                    failed.append({
                        "identifier": identifier,
                        "card_id": card.get("id"),
                        "error": error_msg
                    })
            
            print(f"[SUCCESS] Updated {len(updated)} jobs")
            if failed:
                print(f"[WARNING] Failed to update {len(failed)} jobs")
        else:
            print(f"\n[STEP 4] Would update {len(matched_cards)} jobs")
            print("[INFO] Run with --execute to actually update the database")
        
        # Build result
        result = {
            "total_cards": len(trello_cards),
            "matched": len(matched_cards),
            "unmatched": len(unmatched_cards),
            "updated": len(updated) if execute else 0,
            "failed": len(failed) if execute else 0,
            "executed": execute,
            "unmatched_details": unmatched_cards[:50],  # Limit to first 50
            "failed_details": failed[:50] if execute else []  # Limit to first 50
        }
        
        # Print summary
        print("\n" + "=" * 80)
        print("REBUILD RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Total Trello cards: {len(trello_cards)}")
        print(f"  Matched to jobs: {len(matched_cards)}")
        print(f"  Unmatched cards: {len(unmatched_cards)}")
        
        if execute:
            print(f"  ✅ Updated: {len(updated)} jobs")
            if failed:
                print(f"  ❌ Failed: {len(failed)} jobs")
            
            if len(updated) > 0:
                print(f"\n✅ SUCCESS: Rebuilt Trello data for {len(updated)} jobs!")
            if failed:
                print(f"\n⚠️  WARNING: Failed to update {len(failed)} jobs")
        else:
            print(f"  Would update: {len(matched_cards)} jobs")
            print(f"\n💡 TIP: Run with --execute to actually rebuild the data")
        
        if unmatched_cards:
            print(f"\n📋 UNMATCHED CARDS:")
            print(f"  These cards could not be matched to jobs in the database.")
            print(f"  They may be:")
            print(f"    - Cards with invalid identifier format")
            print(f"    - Cards for jobs not in the database")
            print(f"    - Cards with no identifier in the name")
        
        print("\n" + "=" * 80)
        
        return result
        
    except Exception as e:
        error_msg = f"Rebuild failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        print(f"\n[ERROR] {error_msg}")
        
        # Rollback on error
        if execute:
            db.session.rollback()
            print("[INFO] Database changes have been rolled back")
        
        import traceback
        print(traceback.format_exc())
        return {
            "error": error_msg,
            "error_type": type(e).__name__,
            "executed": execute
        }


if __name__ == "__main__":
    from app import create_app
    
    parser = argparse.ArgumentParser(description="Rebuild Trello data from existing Trello cards")
    parser.add_argument("--execute", action="store_true", 
                       help="Actually update the database (default: dry run only)")
    
    args = parser.parse_args()
    
    app = create_app()
    with app.app_context():
        rebuild_trello_data(execute=args.execute)

