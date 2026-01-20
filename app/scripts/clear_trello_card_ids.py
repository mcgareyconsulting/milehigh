"""
Clear all Trello-related data from the database.

This script clears all Trello fields from jobs:
- trello_card_id
- trello_card_name
- trello_list_id
- trello_list_name
- trello_card_description
- trello_card_date

This is useful when switching to a new Trello board and you need to
clear all existing Trello data so new cards can be created.

Usage:
    python -m app.scripts.clear_trello_card_ids          # Preview only (dry run)
    python -m app.scripts.clear_trello_card_ids --execute  # Actually clear the data
"""

import argparse
from app.models import Job, db
from app.logging_config import get_logger

logger = get_logger(__name__)


def clear_trello_card_ids(execute=False):
    """
    Clear all Trello-related data from the database.
    
    Clears the following fields:
    - trello_card_id
    - trello_card_name
    - trello_list_id
    - trello_list_name
    - trello_card_description
    - trello_card_date
    
    Args:
        execute: If True, actually clear the data (default: False for safety)
    
    Returns:
        dict with clearing results
    """
    print("=" * 80)
    print("CLEAR ALL TRELLO DATA")
    print("=" * 80)
    mode = "DRY RUN (Preview Only)" if not execute else "LIVE MODE - WILL CLEAR ALL TRELLO DATA"
    print(f"\n[INFO] Mode: {mode}")
    
    if not execute:
        print("[WARNING] This is a dry run. Use --execute to actually clear the data.")
    
    try:
        # Step 1: Count jobs with Trello data
        print("\n[STEP 1] Counting jobs with Trello data...")
        
        jobs_with_cards = Job.query.filter(Job.trello_card_id.isnot(None)).all()
        total_jobs = Job.query.count()
        jobs_without_cards = Job.query.filter(Job.trello_card_id.is_(None)).count()
        
        # Count jobs with various Trello fields
        jobs_with_name = Job.query.filter(Job.trello_card_name.isnot(None)).count()
        jobs_with_list = Job.query.filter(Job.trello_list_id.isnot(None)).count()
        jobs_with_description = Job.query.filter(Job.trello_card_description.isnot(None)).count()
        
        print(f"[INFO] Total jobs in database: {total_jobs}")
        print(f"[INFO] Jobs with trello_card_id: {len(jobs_with_cards)}")
        print(f"[INFO] Jobs with trello_card_name: {jobs_with_name}")
        print(f"[INFO] Jobs with trello_list_id: {jobs_with_list}")
        print(f"[INFO] Jobs with trello_card_description: {jobs_with_description}")
        print(f"[INFO] Jobs without any Trello data: {jobs_without_cards}")
        
        if len(jobs_with_cards) == 0:
            print("[INFO] No jobs have Trello data set. Nothing to clear.")
            return {
                "total_jobs": total_jobs,
                "jobs_with_cards": 0,
                "cleared": 0,
                "executed": execute
            }
        
        # Step 2: Show sample of what will be cleared
        print(f"\n[STEP 2] Sample of jobs that will be cleared:")
        for job in jobs_with_cards[:10]:  # Show first 10
            print(f"  - {job.job}-{job.release}:")
            print(f"      Card ID: {job.trello_card_id}")
            print(f"      List: {job.trello_list_name or 'N/A'}")
        if len(jobs_with_cards) > 10:
            print(f"  ... and {len(jobs_with_cards) - 10} more")
        
        # Step 3: Clear all Trello fields
        if execute:
            print(f"\n[STEP 3] Clearing all Trello data for {len(jobs_with_cards)} jobs...")
            
            # Update all jobs with trello_card_id to clear all Trello fields
            updated_count = Job.query.filter(Job.trello_card_id.isnot(None)).update(
                {
                    Job.trello_card_id: None,
                    Job.trello_card_name: None,
                    Job.trello_list_id: None,
                    Job.trello_list_name: None,
                    Job.trello_card_description: None,
                    Job.trello_card_date: None
                },
                synchronize_session=False
            )
            
            # Commit the changes
            db.session.commit()
            
            print(f"[SUCCESS] Cleared all Trello data for {updated_count} jobs")
            
            # Verify
            remaining_card_id = Job.query.filter(Job.trello_card_id.isnot(None)).count()
            remaining_name = Job.query.filter(Job.trello_card_name.isnot(None)).count()
            remaining_list = Job.query.filter(Job.trello_list_id.isnot(None)).count()
            
            if remaining_card_id == 0 and remaining_name == 0 and remaining_list == 0:
                print(f"[VERIFY] ✅ All Trello data cleared successfully")
            else:
                print(f"[WARNING] ⚠️  Some Trello data remains:")
                print(f"          - trello_card_id: {remaining_card_id}")
                print(f"          - trello_card_name: {remaining_name}")
                print(f"          - trello_list_id: {remaining_list}")
        else:
            print(f"\n[STEP 3] Would clear all Trello data for {len(jobs_with_cards)} jobs")
            print("[INFO] This will clear:")
            print("       - trello_card_id")
            print("       - trello_card_name")
            print("       - trello_list_id")
            print("       - trello_list_name")
            print("       - trello_card_description")
            print("       - trello_card_date")
            print("[INFO] Run with --execute to actually clear the data")
        
        # Build result
        result = {
            "total_jobs": total_jobs,
            "jobs_with_cards": len(jobs_with_cards),
            "cleared": len(jobs_with_cards) if execute else 0,
            "executed": execute
        }
        
        # Print summary
        print("\n" + "=" * 80)
        print("CLEARING RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Total jobs: {total_jobs}")
        print(f"  Jobs with Trello data: {len(jobs_with_cards)}")
        
        if execute:
            print(f"  ✅ Cleared: {len(jobs_with_cards)} jobs")
            print(f"\n✅ SUCCESS: All Trello data has been cleared!")
            print("   You can now rebuild Trello data by:")
            print("   1. Running the seeding script to create new cards")
            print("   2. Or syncing from Trello to rebuild the data")
        else:
            print(f"  Would clear: {len(jobs_with_cards)} jobs")
            print(f"\n💡 TIP: Run with --execute to actually clear all Trello data")
        
        print("\n" + "=" * 80)
        
        return result
        
    except Exception as e:
        error_msg = f"Clearing failed: {str(e)}"
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
    
    parser = argparse.ArgumentParser(description="Clear all Trello-related data from the database")
    parser.add_argument("--execute", action="store_true", 
                       help="Actually clear the IDs (default: dry run only)")
    
    args = parser.parse_args()
    
    app = create_app()
    with app.app_context():
        clear_trello_card_ids(execute=args.execute)

