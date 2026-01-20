"""
Seed released cards from database to Trello board.

This script:
- Queries jobs from the database with stage="Released" (or None)
- Filters to jobs that don't have a trello_card_id
- Creates Trello cards using the scanner function
- Creates mirror cards in the unassigned list if configured

Usage:
    python -m app.scripts.seed_released_cards          # Run seeding
    python -m app.scripts.seed_released_cards --limit 10  # Limit to 10 jobs
    python -m app.scripts.seed_released_cards --dry-run    # Preview only
"""

import argparse
from app.models import Job, db
from app.trello.scanner import create_trello_card_for_db_job
from app.logging_config import get_logger

logger = get_logger(__name__)


def seed_released_cards(limit=None, dry_run=False):
    """
    Seed released cards from database to Trello board.
    
    Args:
        limit: Maximum number of jobs to process (None for all)
        dry_run: If True, only preview what would be created (default: False)
    
    Returns:
        dict with seeding results
    """
    print("=" * 80)
    print("SEED RELEASED CARDS TO TRELLO")
    print("=" * 80)
    mode = "DRY RUN (Preview Only)" if dry_run else "LIVE MODE"
    print(f"\n[INFO] Mode: {mode}")
    if limit:
        print(f"[INFO] Processing limit: {limit} jobs")
    
    try:
        # Step 1: Query released jobs without Trello cards
        print("\n[STEP 1] Querying released jobs from database...")
        
        # Query jobs with stage="Released" or stage=None, and no trello_card_id
        query = Job.query.filter(
            db.or_(
                Job.stage == "Released",
                Job.stage.is_(None)
            ),
            Job.trello_card_id.is_(None)
        )
        
        if limit:
            query = query.limit(limit)
        
        jobs = query.all()
        
        print(f"[INFO] Found {len(jobs)} released jobs without Trello cards")
        
        if len(jobs) == 0:
            print("[INFO] No jobs to seed")
            return {
                "total_jobs": 0,
                "created": 0,
                "failed": 0,
                "skipped": 0,
                "dry_run": dry_run
            }
        
        # Step 2: Create Trello cards
        print(f"\n[STEP 2] {'Previewing' if dry_run else 'Creating'} Trello cards...")
        
        created = []
        failed = []
        skipped = []
        
        for idx, job in enumerate(jobs, 1):
            job_id = f"{job.job}-{job.release}"
            
            try:
                if dry_run:
                    print(f"[PREVIEW] Would create card for {job_id}: {job.job_name or 'Unknown Job'}")
                    created.append({
                        "job_id": job_id,
                        "job": job.job,
                        "release": job.release,
                        "job_name": job.job_name,
                        "description": job.description,
                        "status": "preview"
                    })
                else:
                    print(f"[{idx}/{len(jobs)}] Creating card for {job_id}...")
                    
                    # Use the scanner function which now includes mirror card creation
                    result = create_trello_card_for_db_job(job, list_name="Released")
                    
                    if result.get("success"):
                        mirror_info = ""
                        if result.get("mirror_card_id"):
                            mirror_info = f" (mirror: {result['mirror_card_id']})"
                        print(f"[SUCCESS] Created card {result['card_id']} for {job_id}{mirror_info}")
                        created.append({
                            "job_id": job_id,
                            "card_id": result.get("card_id"),
                            "mirror_card_id": result.get("mirror_card_id"),
                            "job": job.job,
                            "release": job.release,
                            "job_name": job.job_name,
                            "status": "created"
                        })
                    else:
                        error = result.get("error", "Unknown error")
                        if "already exists" in error.lower():
                            print(f"[SKIP] {job_id}: {error}")
                            skipped.append({
                                "job_id": job_id,
                                "job": job.job,
                                "release": job.release,
                                "reason": error,
                                "status": "skipped"
                            })
                        else:
                            print(f"[ERROR] Failed to create card for {job_id}: {error}")
                            failed.append({
                                "job_id": job_id,
                                "job": job.job,
                                "release": job.release,
                                "error": error,
                                "status": "failed"
                            })
            
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error processing {job_id}: {error_msg}", exc_info=True)
                print(f"[ERROR] Exception processing {job_id}: {error_msg}")
                failed.append({
                    "job_id": job_id,
                    "job": job.job,
                    "release": job.release,
                    "error": error_msg,
                    "status": "failed"
                })
        
        # Build result
        result = {
            "total_jobs": len(jobs),
            "created": len(created),
            "failed": len(failed),
            "skipped": len(skipped),
            "dry_run": dry_run,
            "created_details": created[:50],  # Limit to first 50
            "failed_details": failed[:50],  # Limit to first 50
            "skipped_details": skipped[:50]  # Limit to first 50
        }
        
        # Print summary
        print("\n" + "=" * 80)
        print("SEEDING RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Total jobs found: {len(jobs)}")
        if dry_run:
            print(f"  Would create: {len(created)} cards")
        else:
            print(f"  ✅ Created: {len(created)} cards")
            print(f"  ⚠️  Skipped: {len(skipped)} jobs")
            print(f"  ❌ Failed: {len(failed)} jobs")
        
        if created and not dry_run:
            mirror_count = sum(1 for item in created if item.get("mirror_card_id"))
            print(f"  🔗 Mirror cards created: {mirror_count}")
        
        if failed:
            print(f"\n❌ FAILED JOBS:")
            for item in failed[:10]:  # Show first 10
                print(f"  - {item.get('job_id', 'Unknown')}: {item.get('error', 'Unknown error')}")
        
        if skipped:
            print(f"\n⚠️  SKIPPED JOBS:")
            for item in skipped[:10]:  # Show first 10
                print(f"  - {item.get('job_id', 'Unknown')}: {item.get('reason', 'Unknown reason')}")
        
        if not dry_run and len(created) > 0:
            print(f"\n✅ SUCCESS: Created {len(created)} Trello card(s)!")
        elif dry_run:
            print(f"\n💡 TIP: Run without --dry-run to actually create {len(created)} card(s)")
        
        print("\n" + "=" * 80)
        
        return result
        
    except Exception as e:
        error_msg = f"Seeding failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        print(f"\n[ERROR] {error_msg}")
        import traceback
        print(traceback.format_exc())
        return {
            "error": error_msg,
            "error_type": type(e).__name__,
            "dry_run": dry_run
        }


if __name__ == "__main__":
    from app import create_app
    
    parser = argparse.ArgumentParser(description="Seed released cards from database to Trello board")
    parser.add_argument("--limit", type=int, help="Maximum number of jobs to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't create cards")
    
    args = parser.parse_args()
    
    app = create_app()
    with app.app_context():
        seed_released_cards(limit=args.limit, dry_run=args.dry_run)

