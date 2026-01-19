"""
Backfill script to collect viewer_url for all jobs in the database.

This script:
- Iterates through all jobs in the database
- Collects viewer_url from Procore for each job
- Updates the viewer_url field in the database
- Does NOT update Trello cards (only collects and stores URLs)
- Logs errors and continues processing

Usage:
    python -m app.scripts.backfill_viewer_urls
"""

from app.models import Job, db
from app.procore.procore import get_viewer_url_for_job
import logging

logger = logging.getLogger(__name__)


def backfill_viewer_urls(return_json=False):
    """
    Backfill viewer_url for all jobs in the database.
    
    Args:
        return_json: If True, returns a dictionary instead of printing
    
    Returns:
        dict with backfill results if return_json=True, None otherwise
    """
    if not return_json:
        print("=" * 80)
        print("BACKFILL VIEWER URLS")
        print("=" * 80)
        print("\n[INFO] Collecting viewer_url for all jobs from Procore")
        print("[INFO] This will update all jobs (overwriting existing viewer_url values)")
        print("[INFO] Trello cards will NOT be updated")
    
    try:
        # Get all jobs from database
        if not return_json:
            print("\n[STEP 1] Loading all jobs from database...")
        
        all_jobs = Job.query.all()
        total_jobs = len(all_jobs)
        
        if not return_json:
            print(f"[INFO] Found {total_jobs} jobs to process")
        
        if total_jobs == 0:
            if return_json:
                return {"message": "No jobs found in database", "total_jobs": 0}
            print("[INFO] No jobs found in database")
            return
        
        # Process each job
        if not return_json:
            print("\n[STEP 2] Processing jobs...")
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        errors = []
        successes = []
        
        for idx, job in enumerate(all_jobs, 1):
            job_number = job.job
            release_number = job.release
            identifier = f"{job_number}-{release_number}"
            
            try:
                # Get viewer_url from Procore
                result = get_viewer_url_for_job(job_number, release_number)
                
                if result and result.get("success"):
                    viewer_url = result.get("viewer_url")
                    
                    # Update job record
                    job.viewer_url = viewer_url
                    db.session.commit()
                    
                    success_count += 1
                    successes.append({
                        "job": job_number,
                        "release": release_number,
                        "identifier": identifier,
                        "viewer_url": viewer_url
                    })
                    
                    if not return_json and idx % 10 == 0:
                        print(f"[INFO] Processed {idx}/{total_jobs} jobs... (Success: {success_count}, Errors: {error_count})")
                else:
                    error_count += 1
                    error_msg = result.get("error", "Unknown error") if result else "No result returned"
                    errors.append({
                        "job": job_number,
                        "release": release_number,
                        "identifier": identifier,
                        "error": error_msg
                    })
                    
                    # Log the error
                    logger.warning(
                        "Failed to get viewer_url for job=%s release=%s: %s",
                        job_number,
                        release_number,
                        error_msg
                    )
                    
                    if not return_json and idx % 10 == 0:
                        print(f"[INFO] Processed {idx}/{total_jobs} jobs... (Success: {success_count}, Errors: {error_count})")
            
            except Exception as e:
                error_count += 1
                error_msg = f"Exception processing job: {str(e)}"
                errors.append({
                    "job": job_number,
                    "release": release_number,
                    "identifier": identifier,
                    "error": error_msg
                })
                
                logger.error(
                    "Exception processing job=%s release=%s: %s",
                    job_number,
                    release_number,
                    str(e),
                    exc_info=True
                )
                
                # Continue processing other jobs
                continue
        
        # Build result
        result = {
            "total_jobs": total_jobs,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": f"{(success_count / total_jobs * 100):.1f}%" if total_jobs > 0 else "0%",
            "errors": errors[:50],  # Limit to first 50 for response size
            "successes": successes[:50] if return_json else []  # Only include in JSON mode
        }
        
        if return_json:
            return result
        
        # Print summary
        print("\n" + "=" * 80)
        print("BACKFILL RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Total jobs processed: {total_jobs}")
        print(f"  ✅ Successfully updated: {success_count}")
        print(f"  ❌ Errors: {error_count}")
        if total_jobs > 0:
            print(f"  📈 Success rate: {(success_count / total_jobs * 100):.1f}%")
        
        if errors:
            print(f"\n❌ ERRORS ({len(errors)} total):")
            # Group errors by type
            error_types = {}
            for error in errors:
                error_msg = error.get("error", "Unknown error")
                # Extract error type (first part before colon or first 50 chars)
                error_type = error_msg.split(":")[0] if ":" in error_msg else error_msg[:50]
                if error_type not in error_types:
                    error_types[error_type] = []
                error_types[error_type].append(error)
            
            for error_type, error_list in list(error_types.items())[:10]:  # Show first 10 error types
                print(f"  - {error_type}: {len(error_list)} jobs")
                # Show first 3 examples
                for error in error_list[:3]:
                    identifier = error.get("identifier", "Unknown")
                    print(f"    • {identifier}")
                if len(error_list) > 3:
                    print(f"    ... and {len(error_list) - 3} more")
        
        if success_count > 0:
            print(f"\n✅ SUCCESS: Updated viewer_url for {success_count} job(s)")
        
        if error_count > 0:
            print(f"\n⚠️  WARNING: {error_count} job(s) could not be updated")
            print("   Check logs for detailed error information")
        
        print("\n" + "=" * 80)
        
        return result
        
    except Exception as e:
        error_msg = f"Backfill failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if return_json:
            return {"error": error_msg, "error_type": type(e).__name__}
        print(f"\n[ERROR] {error_msg}")
        import traceback
        print(traceback.format_exc())
        return None


if __name__ == "__main__":
    from app import create_app
    
    app = create_app()
    with app.app_context():
        backfill_viewer_urls()

