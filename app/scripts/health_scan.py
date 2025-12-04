"""
Health scan script to identify jobs missing from the database.

This script:
- Scans OneDrive (Excel) for all jobs with valid identifiers
- Scans relevant Trello lists (Released through Shipping completed) for all cards
- Compares both against the database (source of truth) to find missing jobs
- Returns a comprehensive report of missing jobs

Usage:
    python -m app.scripts.health_scan          # Run scan
"""

from app.models import Job, db
from app.trello.api import get_trello_cards_from_subset, get_trello_card_by_id, update_trello_card_name, get_expected_card_name
from app.trello.utils import extract_identifier
from app.onedrive.api import get_excel_dataframe
import logging

logger = logging.getLogger(__name__)


def health_scan(return_json=False):
    """
    Perform a comprehensive health scan to find jobs missing from the database.
    
    The database is the source of truth. This function identifies:
    1. Jobs in OneDrive (Excel) that are missing from the DB
    2. Jobs in Trello lists (released through shipping completed) that are missing from the DB
    
    Args:
        return_json: If True, returns a dictionary instead of printing
    
    Returns:
        dict with scan results if return_json=True, None otherwise
    """
    if not return_json:
        print("=" * 80)
        print("HEALTH SCAN: Identifying Jobs Missing from Database")
        print("=" * 80)
        print("\n[INFO] Database is the source of truth")
        print("[INFO] Scanning OneDrive (Excel) and Trello lists...")
    
    try:
        # Step 1: Get all jobs from database
        if not return_json:
            print("\n[STEP 1] Loading jobs from database...")
        
        db_jobs = Job.query.all()
        db_identifiers = set()
        for job in db_jobs:
            identifier = f"{job.job}-{job.release}"
            db_identifiers.add(identifier)
        
        if not return_json:
            print(f"[INFO] Found {len(db_identifiers)} unique job identifiers in database")
        
        # Step 2: Get all jobs from OneDrive (Excel)
        if not return_json:
            print("\n[STEP 2] Loading jobs from OneDrive (Excel)...")
        
        try:
            df = get_excel_dataframe()
            df["identifier"] = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)
            
            # Filter to only rows with valid job-release identifiers
            excel_identifiers = set()
            excel_jobs_data = {}
            
            for _, row in df.iterrows():
                identifier = row["identifier"]
                job_num = row.get("Job #")
                release_str = str(row.get("Release #", "")).strip()
                
                # Validate job number is an integer
                try:
                    job_num = int(job_num)
                    excel_identifiers.add(identifier)
                    excel_jobs_data[identifier] = {
                        "job": job_num,
                        "release": release_str,
                        "job_name": row.get("Job", ""),
                        "description": row.get("Description", ""),
                        "ship": row.get("Ship", ""),
                        "trello_list": None  # Excel doesn't have Trello list info
                    }
                except (ValueError, TypeError):
                    # Skip rows with invalid job numbers
                    continue
            
            if not return_json:
                print(f"[INFO] Found {len(excel_identifiers)} unique job identifiers in OneDrive")
        
        except Exception as e:
            error_msg = f"Error loading OneDrive data: {str(e)}"
            logger.error(error_msg)
            if not return_json:
                print(f"[ERROR] {error_msg}")
            excel_identifiers = set()
            excel_jobs_data = {}
        
        # Step 3: Get all cards from relevant Trello lists
        if not return_json:
            print("\n[STEP 3] Loading cards from Trello lists...")
            print("[INFO] Scanning lists: Released, Fit Up Complete., Paint complete, Shipping completed, Store at MHMW for shipping, Shipping planning")
        
        try:
            trello_cards = get_trello_cards_from_subset()
            trello_identifiers = set()
            trello_jobs_data = {}
            
            for card in trello_cards:
                name = (card.get("name") or "").strip()
                if not name:
                    continue
                
                identifier = extract_identifier(name)
                if identifier:
                    trello_identifiers.add(identifier)
                    trello_jobs_data[identifier] = {
                        "card_id": card.get("id"),
                        "card_name": card.get("name", ""),
                        "list_name": card.get("list_name", ""),
                        "list_id": card.get("list_id"),
                        "job": None,  # Will extract from identifier if possible
                        "release": None
                    }
                    
                    # Try to extract job and release from identifier
                    parts = identifier.split("-")
                    if len(parts) == 2:
                        try:
                            trello_jobs_data[identifier]["job"] = int(parts[0])
                            trello_jobs_data[identifier]["release"] = parts[1]
                        except (ValueError, TypeError):
                            pass
            
            if not return_json:
                print(f"[INFO] Found {len(trello_identifiers)} unique job identifiers in Trello lists")
        
        except Exception as e:
            error_msg = f"Error loading Trello data: {str(e)}"
            logger.error(error_msg)
            if not return_json:
                print(f"[ERROR] {error_msg}")
            trello_identifiers = set()
            trello_jobs_data = {}
        
        # Step 4: Find missing jobs
        if not return_json:
            print("\n[STEP 4] Comparing against database to find missing jobs...")
        
        # Jobs in Excel but not in DB
        missing_from_db_excel = excel_identifiers - db_identifiers
        missing_excel_details = [
            excel_jobs_data[ident] for ident in missing_from_db_excel
            if ident in excel_jobs_data
        ]
        
        # Jobs in Trello but not in DB
        missing_from_db_trello = trello_identifiers - db_identifiers
        missing_trello_details = [
            trello_jobs_data[ident] for ident in missing_from_db_trello
            if ident in trello_jobs_data
        ]
        
        # Jobs in both Excel and Trello but not in DB (most critical)
        missing_from_db_both = missing_from_db_excel & missing_from_db_trello
        missing_both_details = []
        for ident in missing_from_db_both:
            excel_info = excel_jobs_data.get(ident, {})
            trello_info = trello_jobs_data.get(ident, {})
            missing_both_details.append({
                "identifier": ident,
                "excel": excel_info,
                "trello": trello_info
            })
        
        # Jobs in Excel only (not in Trello, not in DB)
        missing_excel_only = missing_from_db_excel - trello_identifiers
        missing_excel_only_details = [
            {
                "identifier": ident,
                "excel": excel_jobs_data.get(ident, {}),
                "trello": None
            }
            for ident in missing_excel_only
        ]
        
        # Jobs in Trello only (not in Excel, not in DB)
        missing_trello_only = missing_from_db_trello - excel_identifiers
        missing_trello_only_details = [
            {
                "identifier": ident,
                "excel": None,
                "trello": trello_jobs_data.get(ident, {})
            }
            for ident in missing_trello_only
        ]
        
        # Build summary
        total_missing = len(missing_from_db_excel | missing_from_db_trello)
        
        result = {
            "database": {
                "total_jobs": len(db_identifiers),
                "identifiers": sorted(list(db_identifiers))[:50]  # First 50 for preview
            },
            "onedrive": {
                "total_jobs": len(excel_identifiers),
                "identifiers": sorted(list(excel_identifiers))[:50]  # First 50 for preview
            },
            "trello": {
                "total_jobs": len(trello_identifiers),
                "identifiers": sorted(list(trello_identifiers))[:50]  # First 50 for preview
            },
            "missing_jobs": {
                "total_missing": total_missing,
                "in_excel_and_trello_but_not_db": {
                    "count": len(missing_from_db_both),
                    "identifiers": sorted(list(missing_from_db_both)),
                    "details": missing_both_details[:20]  # Limit to first 20 for response size
                },
                "in_excel_only_not_in_db": {
                    "count": len(missing_excel_only),
                    "identifiers": sorted(list(missing_excel_only)),
                    "details": missing_excel_only_details[:20]  # Limit to first 20
                },
                "in_trello_only_not_in_db": {
                    "count": len(missing_trello_only),
                    "identifiers": sorted(list(missing_trello_only)),
                    "details": missing_trello_only_details[:20]  # Limit to first 20
                }
            },
            "summary": {
                "db_total": len(db_identifiers),
                "excel_total": len(excel_identifiers),
                "trello_total": len(trello_identifiers),
                "missing_total": total_missing,
                "missing_in_both": len(missing_from_db_both),
                "missing_excel_only": len(missing_excel_only),
                "missing_trello_only": len(missing_trello_only)
            }
        }
        
        if return_json:
            return result
        
        # Print summary
        print("\n" + "=" * 80)
        print("HEALTH SCAN RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Database (source of truth): {len(db_identifiers)} jobs")
        print(f"  OneDrive (Excel):          {len(excel_identifiers)} jobs")
        print(f"  Trello lists:                {len(trello_identifiers)} jobs")
        print(f"  ⚠️  MISSING FROM DB:         {total_missing} jobs")
        
        print(f"\n🔍 BREAKDOWN OF MISSING JOBS:")
        print(f"  In BOTH Excel & Trello but NOT in DB: {len(missing_from_db_both)} jobs")
        print(f"  In Excel ONLY (not in Trello, not in DB): {len(missing_excel_only)} jobs")
        print(f"  In Trello ONLY (not in Excel, not in DB): {len(missing_trello_only)} jobs")
        
        if missing_from_db_both:
            print(f"\n🚨 CRITICAL: Jobs in BOTH Excel & Trello but missing from DB:")
            for detail in missing_both_details[:10]:  # Show first 10
                ident = detail.get("identifier", "Unknown")
                excel_info = detail.get("excel", {})
                trello_info = detail.get("trello", {})
                print(f"  - {ident}: Excel={excel_info.get('job_name', 'N/A')}, Trello List={trello_info.get('list_name', 'N/A')}")
        
        if missing_excel_only:
            print(f"\n📄 Jobs in Excel ONLY (not in Trello, not in DB):")
            for detail in missing_excel_only_details[:10]:  # Show first 10
                ident = detail.get("identifier", "Unknown")
                excel_info = detail.get("excel", {})
                print(f"  - {ident}: {excel_info.get('job_name', 'N/A')}")
        
        if missing_trello_only:
            print(f"\n🃏 Jobs in Trello ONLY (not in Excel, not in DB):")
            for detail in missing_trello_only_details[:10]:  # Show first 10
                ident = detail.get("identifier", "Unknown")
                trello_info = detail.get("trello", {})
                print(f"  - {ident}: {trello_info.get('card_name', 'N/A')} (List: {trello_info.get('list_name', 'N/A')})")
        
        if total_missing == 0:
            print("\n✅ SUCCESS: All jobs from OneDrive and Trello are present in the database!")
        else:
            print(f"\n⚠️  WARNING: {total_missing} job(s) are missing from the database")
            print("   Consider running incremental seeding to add missing jobs.")
        
        print("\n" + "=" * 80)
        
        return result
        
    except Exception as e:
        error_msg = f"Health scan failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if return_json:
            return {"error": error_msg, "error_type": type(e).__name__}
        print(f"\n[ERROR] {error_msg}")
        import traceback
        print(traceback.format_exc())
        return None


def scan_trello_card_names(return_json=False, fix_names=False, limit=None):
    """
    Scan Trello cards for inaccurate names and optionally update them.
    
    The expected card name format is: {job_number}-{release_number} {job_name} {description}
    Some older cards may be missing the description part.
    
    Args:
        return_json: If True, returns a dictionary instead of printing
        fix_names: If True, actually updates the card names (default: False for safety)
        limit: Maximum number of cards to process (None for all)
    
    Returns:
        dict with scan results if return_json=True, None otherwise
    """
    if not return_json:
        print("=" * 80)
        print("TRELLO CARD NAME SCAN")
        print("=" * 80)
        mode = "FIX MODE" if fix_names else "SCAN MODE (Preview Only)"
        print(f"\n[INFO] Mode: {mode}")
        print("[INFO] Expected format: {job}-{release} {job_name} {description}")
        if limit:
            print(f"[INFO] Processing limit: {limit} cards")
    
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
        
        # Scan each card
        if not return_json:
            print("\n[STEP 2] Scanning Trello card names...")
        
        incorrect_names = []
        correct_names = []
        errors = []
        updated_count = 0
        failed_updates = []
        
        for idx, job in enumerate(db_jobs, 1):
            job_id = f"{job.job}-{job.release}"
            
            try:
                # Get current card from Trello
                card_data = get_trello_card_by_id(job.trello_card_id)
                
                if not card_data:
                    errors.append({
                        "job_id": job_id,
                        "card_id": job.trello_card_id,
                        "error": "Card not found in Trello"
                    })
                    continue
                
                current_name = card_data.get("name", "").strip()
                
                # Generate expected name from database
                expected_name = get_expected_card_name(
                    job.job,
                    job.release,
                    job.job_name or "",
                    job.description or ""
                )
                
                # Compare names
                if current_name != expected_name:
                    incorrect_names.append({
                        "job_id": job_id,
                        "card_id": job.trello_card_id,
                        "current_name": current_name,
                        "expected_name": expected_name,
                        "job_name": job.job_name,
                        "description": job.description,
                        "missing_description": not job.description or job.description.strip() == ""
                    })
                    
                    # Update if fix_names is True
                    if fix_names:
                        try:
                            update_trello_card_name(job.trello_card_id, expected_name)
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
                else:
                    correct_names.append({
                        "job_id": job_id,
                        "card_id": job.trello_card_id,
                        "name": current_name
                    })
                
                # Progress indicator
                if not return_json and idx % 50 == 0:
                    print(f"[INFO] Processed {idx}/{len(db_jobs)} cards...")
            
            except Exception as e:
                errors.append({
                    "job_id": job_id,
                    "card_id": job.trello_card_id,
                    "error": str(e)
                })
                if not return_json:
                    print(f"[ERROR] Error processing {job_id}: {e}")
                continue
        
        # Build result
        result = {
            "total_jobs_scanned": len(db_jobs),
            "correct_names": len(correct_names),
            "incorrect_names": len(incorrect_names),
            "errors": len(errors),
            "updated_count": updated_count if fix_names else 0,
            "failed_updates": len(failed_updates) if fix_names else 0,
            "incorrect_name_details": incorrect_names[:50],  # Limit to first 50
            "errors_details": errors[:20],  # Limit to first 20
            "failed_update_details": failed_updates[:20] if fix_names else [],  # Limit to first 20
            "fix_mode": fix_names
        }
        
        if return_json:
            return result
        
        # Print summary
        print("\n" + "=" * 80)
        print("CARD NAME SCAN RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Total jobs scanned: {len(db_jobs)}")
        print(f"  ✅ Correct names: {len(correct_names)}")
        print(f"  ⚠️  Incorrect names: {len(incorrect_names)}")
        print(f"  ❌ Errors: {len(errors)}")
        
        if fix_names:
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
        
        if fix_names and failed_updates:
            print(f"\n❌ FAILED UPDATES:")
            for failed in failed_updates[:5]:  # Show first 5
                print(f"  - {failed.get('job_id', 'Unknown')}: {failed.get('error', 'Unknown error')}")
        
        if len(incorrect_names) == 0:
            print("\n✅ SUCCESS: All Trello card names are correct!")
        elif not fix_names:
            print(f"\n💡 TIP: Run with fix_names=True to update {len(incorrect_names)} incorrect card name(s)")
        
        print("\n" + "=" * 80)
        
        return result
        
    except Exception as e:
        error_msg = f"Card name scan failed: {str(e)}"
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
        health_scan()

