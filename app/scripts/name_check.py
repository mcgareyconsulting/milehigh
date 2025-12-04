"""
Name check scanner to verify and update Trello card names.

This script:
- Checks all jobs in the database that have Trello cards
- Compares trello_card_name (from DB) with expected format: {job}-{release} {job_name} {description}
- Optionally updates Trello card names via API if they don't match

Usage:
    python -m app.scripts.name_check          # Dry run (preview only)
    python -m app.scripts.name_check --update # Actually update cards
"""

from app.models import Job, db
from app.trello.api import update_trello_card_name, get_expected_card_name
import logging

logger = logging.getLogger(__name__)


def check_card_names(return_json=False, dry_run=True, limit=None):
    """
    Check Trello card names against expected format and optionally update them.
    
    Expected format: {job}-{release} {job_name} {description}
    Compares DB trello_card_name field with expected name based on DB values.
    
    Args:
        return_json: If True, returns a dictionary instead of printing
        dry_run: If True, only previews changes without updating (default: True)
        limit: Maximum number of jobs to process (None for all)
    
    Returns:
        dict with scan results if return_json=True, None otherwise
    """
    if not return_json:
        print("=" * 80)
        print("TRELLO CARD NAME CHECK")
        print("=" * 80)
        mode = "DRY RUN (Preview Only)" if dry_run else "UPDATE MODE"
        print(f"\n[INFO] Mode: {mode}")
        print("[INFO] Expected format: {job}-{release} {job_name} {description}")
        if limit:
            print(f"[INFO] Processing limit: {limit} jobs")
    
    try:
        # Get all jobs from database that have Trello cards
        if not return_json:
            print("\n[STEP 1] Loading jobs with Trello cards from database...")
        
        query = Job.query.filter(Job.trello_card_id.isnot(None))
        if limit:
            query = query.limit(limit)
        
        db_jobs = query.all()
        
        if not return_json:
            print(f"[INFO] Found {len(db_jobs)} jobs with Trello cards")
        
        if len(db_jobs) == 0:
            if return_json:
                return {"message": "No jobs with Trello cards found", "total_jobs": 0}
            print("[INFO] No jobs with Trello cards found")
            return
        
        # Check each card name
        if not return_json:
            print("\n[STEP 2] Checking card names...")
        
        correct_names = []
        incorrect_names = []
        errors = []
        updated_count = 0
        failed_updates = []
        
        for idx, job in enumerate(db_jobs, 1):
            job_id = f"{job.job}-{job.release}"
            
            try:
                # Generate expected name from database values
                expected_name = get_expected_card_name(
                    job.job,
                    job.release,
                    job.job_name or "",
                    job.description or ""
                )
                
                # Get current name from database
                current_name = job.trello_card_name or ""
                
                # Compare names
                if current_name.strip() == expected_name.strip():
                    correct_names.append({
                        "job_id": job_id,
                        "card_id": job.trello_card_id,
                        "name": current_name
                    })
                else:
                    incorrect_names.append({
                        "job_id": job_id,
                        "card_id": job.trello_card_id,
                        "current_name": current_name,
                        "expected_name": expected_name,
                        "job_name": job.job_name,
                        "description": job.description,
                        "missing_description": not job.description or job.description.strip() == ""
                    })
                    
                    # Update if not dry run
                    if not dry_run:
                        try:
                            update_trello_card_name(job.trello_card_id, expected_name)
                            
                            # Also update the DB field to match
                            job.trello_card_name = expected_name
                            db.session.add(job)
                            
                            updated_count += 1
                            incorrect_names[-1]["updated"] = True
                            if not return_json:
                                print(f"[SUCCESS] Updated {job_id}: '{current_name[:50]}...' -> '{expected_name[:50]}...'")
                        except Exception as e:
                            failed_updates.append({
                                "job_id": job_id,
                                "card_id": job.trello_card_id,
                                "error": str(e)
                            })
                            incorrect_names[-1]["updated"] = False
                            incorrect_names[-1]["update_error"] = str(e)
                            if not return_json:
                                print(f"[ERROR] Failed to update {job_id}: {e}")
                
                # Progress indicator
                if not return_json and idx % 50 == 0:
                    print(f"[INFO] Processed {idx}/{len(db_jobs)} jobs...")
            
            except Exception as e:
                errors.append({
                    "job_id": job_id,
                    "card_id": job.trello_card_id,
                    "error": str(e)
                })
                if not return_json:
                    print(f"[ERROR] Error processing {job_id}: {e}")
                continue
        
        # Commit DB updates if any were made
        if not dry_run and updated_count > 0:
            try:
                db.session.commit()
                if not return_json:
                    print(f"\n[INFO] Committed {updated_count} database updates")
            except Exception as e:
                db.session.rollback()
                if not return_json:
                    print(f"\n[ERROR] Failed to commit database updates: {e}")
                logger.error(f"Failed to commit database updates: {e}")
        
        # Build result
        result = {
            "total_jobs_scanned": len(db_jobs),
            "correct_names": len(correct_names),
            "incorrect_names": len(incorrect_names),
            "errors": len(errors),
            "updated_count": updated_count if not dry_run else 0,
            "failed_updates": len(failed_updates) if not dry_run else 0,
            "dry_run": dry_run,
            "incorrect_name_details": incorrect_names[:50],  # Limit to first 50
            "errors_details": errors[:20],  # Limit to first 20
            "failed_update_details": failed_updates[:20] if not dry_run else []  # Limit to first 20
        }
        
        if return_json:
            return result
        
        # Print summary
        print("\n" + "=" * 80)
        print("CARD NAME CHECK RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Total jobs scanned: {len(db_jobs)}")
        print(f"  ✅ Correct names: {len(correct_names)}")
        print(f"  ⚠️  Incorrect names: {len(incorrect_names)}")
        print(f"  ❌ Errors: {len(errors)}")
        
        if not dry_run:
            print(f"\n🔧 UPDATES:")
            print(f"  Successfully updated: {updated_count}")
            print(f"  Failed updates: {len(failed_updates)}")
        
        if incorrect_names:
            print(f"\n⚠️  CARDS WITH INCORRECT NAMES:")
            missing_desc_count = sum(1 for item in incorrect_names if item.get("missing_description"))
            print(f"  Total: {len(incorrect_names)}")
            print(f"  Missing description: {missing_desc_count}")
            
            # Show first 10 examples
            for item in incorrect_names[:10]:
                job_id = item.get("job_id", "Unknown")
                current = item.get("current_name", "")[:60]
                expected = item.get("expected_name", "")[:60]
                missing_desc = " (missing description)" if item.get("missing_description") else ""
                updated = " [UPDATED]" if item.get("updated") else ""
                print(f"  - {job_id}{missing_desc}{updated}")
                print(f"    Current:  {current}...")
                print(f"    Expected: {expected}...")
        
        if errors:
            print(f"\n❌ ERRORS:")
            for error in errors[:5]:  # Show first 5
                print(f"  - {error.get('job_id', 'Unknown')}: {error.get('error', 'Unknown error')}")
        
        if not dry_run and failed_updates:
            print(f"\n❌ FAILED UPDATES:")
            for failed in failed_updates[:5]:  # Show first 5
                print(f"  - {failed.get('job_id', 'Unknown')}: {failed.get('error', 'Unknown error')}")
        
        if len(incorrect_names) == 0:
            print("\n✅ SUCCESS: All Trello card names are correct!")
        elif dry_run:
            print(f"\n💡 TIP: Run with dry_run=False to update {len(incorrect_names)} incorrect card name(s)")
        
        print("\n" + "=" * 80)
        
        return result
        
    except Exception as e:
        error_msg = f"Card name check failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if return_json:
            return {"error": error_msg, "error_type": type(e).__name__}
        print(f"\n[ERROR] {error_msg}")
        import traceback
        print(traceback.format_exc())
        return None


if __name__ == "__main__":
    import sys
    from app import create_app
    
    app = create_app()
    with app.app_context():
        # Check for update mode
        dry_run = "--update" not in sys.argv
        check_card_names(dry_run=dry_run)

