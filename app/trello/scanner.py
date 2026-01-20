"""
Trello-DB Scanner: Compare database jobs with Trello cards.

This module provides scanning functionality to identify:
- Jobs that exist in both DB and Trello
- Jobs that exist in DB only (missing from Trello)
- Cards that exist in Trello only (not in DB)
- List mismatches (DB stage doesn't match Trello list)
"""

from typing import Dict, List, Optional, Tuple
from app.models import Job, db
from app.trello.api import get_all_trello_cards
from app.trello.utils import extract_identifier
from app.logging_config import get_logger

logger = get_logger(__name__)

# Stages that don't have dedicated Trello lists but are mapped during sync
# Cut start → Released, Welded QC → Fit Up Complete., Complete → Shipping completed
STAGES_NOT_TRACKED = []  # Empty - all stages map to lists for sync purposes


def get_expected_trello_list_from_stage(stage: Optional[str]) -> Optional[str]:
    """
    Map a database stage to the expected Trello list name.
    
    For sync purposes, untracked stages (Cut start, Welded QC, Complete) 
    are mapped to existing lists:
    - Cut start → Released (first stage)
    - Welded QC → Fit Up Complete. (previous tracked stage)
    - Complete → Shipping completed (final stage)
    
    Args:
        stage: Database stage value
        
    Returns:
        Expected Trello list name, or None if stage is invalid
    """
    if not stage:
        return None
    
    # Special mappings for untracked stages (no dedicated Trello list)
    if stage == 'Cut start':
        return 'Released'  # Map to first tracked list
    if stage == 'Welded QC':
        return 'Fit Up Complete.'  # Map to previous tracked stage
    if stage == 'Complete':
        return 'Shipping completed'  # Map to final tracked list
    
    # Direct mapping: stage name = Trello list name
    # Valid Trello lists: Released, Fit Up Complete., Paint complete, 
    # Store at MHMW for shipping, Shipping planning, Shipping completed
    return stage


def parse_identifier(identifier: str) -> Optional[Tuple[int, str]]:
    """
    Parse a job-release identifier (e.g., "123-456" or "123-V456") into job and release.
    
    Args:
        identifier: Identifier string like "123-456" or "123-V456"
        
    Returns:
        Tuple of (job_number, release_number) or None if parsing fails
    """
    if not identifier:
        return None
    
    parts = identifier.split("-", 1)
    if len(parts) != 2:
        return None
    
    try:
        job_number = int(parts[0])
        release_number = parts[1].strip()
        return (job_number, release_number)
    except (ValueError, TypeError):
        return None


def scan_trello_db_comparison() -> Dict:
    """
    Scan and compare database jobs with Trello cards.
    
    Returns:
        Dictionary with comparison results:
        {
            "summary": {
                "db_total": int,
                "trello_total": int,
                "in_both": int,
                "db_only": int,
                "trello_only": int,
                "list_mismatches": int
            },
            "in_both": [
                {
                    "job": int,
                    "release": str,
                    "identifier": str,
                    "db_stage": str or None,
                    "trello_list": str,
                    "trello_card_id": str,
                    "trello_card_name": str,
                    "list_mismatch": bool,
                    "expected_list": str or None
                }
            ],
            "db_only": [
                {
                    "job": int,
                    "release": str,
                    "identifier": str,
                    "stage": str or None,
                    "job_name": str
                }
            ],
            "trello_only": [
                {
                    "identifier": str,
                    "trello_card_id": str,
                    "trello_card_name": str,
                    "trello_list": str,
                    "job": int or None,
                    "release": str or None
                }
            ],
            "list_mismatches": [
                {
                    "job": int,
                    "release": str,
                    "identifier": str,
                    "db_stage": str,
                    "trello_list": str,
                    "expected_list": str or None,
                    "trello_card_id": str,
                    "trello_card_name": str
                }
            ]
        }
    """
    logger.info("Starting Trello-DB scanner comparison")
    
    # Step 1: Get all DB jobs
    logger.info("Fetching all jobs from database...")
    db_jobs = Job.query.all()
    db_jobs_by_identifier = {}
    db_identifiers = set()
    
    for job in db_jobs:
        identifier = f"{job.job}-{job.release}"
        db_identifiers.add(identifier)
        db_jobs_by_identifier[identifier] = job
    
    logger.info(f"Found {len(db_jobs)} jobs in database")
    
    # Step 2: Get all Trello cards
    logger.info("Fetching all Trello cards from board...")
    try:
        trello_cards = get_all_trello_cards()
    except Exception as e:
        logger.error(f"Error fetching Trello cards: {e}")
        return {
            "error": f"Failed to fetch Trello cards: {str(e)}",
            "summary": {
                "db_total": len(db_jobs),
                "trello_total": 0,
                "in_both": 0,
                "db_only": len(db_jobs),
                "trello_only": 0,
                "list_mismatches": 0
            },
            "in_both": [],
            "db_only": [
                {
                    "job": job.job,
                    "release": job.release,
                    "identifier": f"{job.job}-{job.release}",
                    "stage": job.stage,
                    "job_name": job.job_name
                }
                for job in db_jobs
            ],
            "trello_only": [],
            "list_mismatches": []
        }
    
    # Step 3: Extract identifiers from Trello cards
    trello_cards_by_identifier = {}
    trello_identifiers = set()
    
    for card in trello_cards:
        card_name = (card.get("name") or "").strip()
        if not card_name:
            continue
        
        identifier = extract_identifier(card_name)
        if identifier:
            trello_identifiers.add(identifier)
            # Store first card for each identifier (in case of duplicates)
            if identifier not in trello_cards_by_identifier:
                trello_cards_by_identifier[identifier] = card
    
    logger.info(f"Found {len(trello_cards)} Trello cards, {len(trello_identifiers)} with valid identifiers")
    
    # Step 4: Build comparison results
    in_both = []
    db_only = []
    trello_only = []
    list_mismatches = []
    
    # Find jobs in both
    for identifier in db_identifiers & trello_identifiers:
        job = db_jobs_by_identifier[identifier]
        card = trello_cards_by_identifier[identifier]
        
        db_stage = job.stage
        trello_list = card.get("list_name", "Unknown")
        expected_list = get_expected_trello_list_from_stage(db_stage)
        
        # Check for list mismatch (only if stage is tracked in Trello)
        list_mismatch = False
        if expected_list is not None and trello_list != expected_list:
            list_mismatch = True
        
        in_both.append({
            "job": job.job,
            "release": job.release,
            "identifier": identifier,
            "db_stage": db_stage,
            "trello_list": trello_list,
            "trello_card_id": card.get("id"),
            "trello_card_name": card.get("name", ""),
            "list_mismatch": list_mismatch,
            "expected_list": expected_list
        })
        
        if list_mismatch:
            list_mismatches.append({
                "job": job.job,
                "release": job.release,
                "identifier": identifier,
                "db_stage": db_stage,
                "trello_list": trello_list,
                "expected_list": expected_list,
                "trello_card_id": card.get("id"),
                "trello_card_name": card.get("name", "")
            })
    
    # Find jobs in DB only
    for identifier in db_identifiers - trello_identifiers:
        job = db_jobs_by_identifier[identifier]
        db_only.append({
            "job": job.job,
            "release": job.release,
            "identifier": identifier,
            "stage": job.stage,
            "job_name": job.job_name
        })
    
    # Find cards in Trello only
    for identifier in trello_identifiers - db_identifiers:
        card = trello_cards_by_identifier[identifier]
        parsed = parse_identifier(identifier)
        
        trello_only.append({
            "identifier": identifier,
            "trello_card_id": card.get("id"),
            "trello_card_name": card.get("name", ""),
            "trello_list": card.get("list_name", "Unknown"),
            "job": parsed[0] if parsed else None,
            "release": parsed[1] if parsed else None
        })
    
    # Build summary
    summary = {
        "db_total": len(db_jobs),
        "trello_total": len(trello_cards),
        "trello_with_identifiers": len(trello_identifiers),
        "in_both": len(in_both),
        "db_only": len(db_only),
        "trello_only": len(trello_only),
        "list_mismatches": len(list_mismatches)
    }
    
    logger.info(f"Scan complete: {summary}")
    
    return {
        "summary": summary,
        "in_both": in_both,
        "db_only": db_only,
        "trello_only": trello_only,
        "list_mismatches": list_mismatches
    }


def delete_trello_card(card_id: str) -> Dict:
    """
    Delete a Trello card by card ID.
    
    Args:
        card_id: Trello card ID
        
    Returns:
        Dictionary with success status and result
    """
    from app.config import Config as cfg
    import requests
    
    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN
    }
    
    try:
        logger.info(f"Deleting Trello card: {card_id}")
        response = requests.delete(url, params=params)
        response.raise_for_status()
        logger.info(f"Successfully deleted Trello card: {card_id}")
        return {"success": True, "card_id": card_id}
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"HTTP error deleting card {card_id}: {http_err}"
        logger.error(error_msg)
        return {"success": False, "card_id": card_id, "error": str(http_err)}
    except Exception as err:
        error_msg = f"Error deleting card {card_id}: {err}"
        logger.error(error_msg)
        return {"success": False, "card_id": card_id, "error": str(err)}


def create_trello_card_for_db_job(job: Job, list_name: Optional[str] = None) -> Dict:
    """
    Create a Trello card for a database job.
    
    Args:
        job: Job database object
        list_name: Optional list name to create card in (defaults based on stage)
        
    Returns:
        Dictionary with success status and card info
    """
    from app.trello.api import get_list_by_name, update_job_record_with_trello_data
    from app.trello.card_creation import (
        build_card_title,
        build_card_description,
        create_trello_card_core,
        apply_card_post_creation_features
    )
    from app.config import Config as cfg
    
    try:
        # Skip if job already has a Trello card
        if job.trello_card_id:
            logger.info(f"Job {job.job}-{job.release} already has Trello card {job.trello_card_id}, skipping creation")
            return {"success": False, "error": "Card already exists", "card_id": job.trello_card_id}
        
        # Determine list name from stage if not provided
        if not list_name:
            list_name = get_expected_trello_list_from_stage(job.stage)
            if not list_name:
                list_name = "Released"  # Default fallback
        
        # Get list ID
        target_list = get_list_by_name(list_name)
        if not target_list:
            # Fall back to configured new-card list
            list_id = cfg.NEW_TRELLO_CARD_LIST_ID
            logger.warning(f"List '{list_name}' not found, using default list")
        else:
            list_id = target_list["id"]
        
        # Build card title and description using shared functions
        card_title = build_card_title(
            job.job,
            job.release,
            job.job_name,
            job.description
        )
        
        card_description = build_card_description(
            description=job.description,
            install_hrs=job.install_hrs,
            paint_color=job.paint_color,
            pm=job.pm,
            by=job.by,
            released=job.released
        )
        
        # Create the card using shared core function
        create_result = create_trello_card_core(
            card_title=card_title,
            card_description=card_description,
            list_id=list_id,
            position="top"
        )
        
        if not create_result["success"]:
            return {
                "success": False,
                "job": job.job,
                "release": job.release,
                "error": create_result.get("error", "Failed to create card")
            }
        
        card_data = create_result["card_data"]
        card_id = create_result["card_id"]
        
        # Update the job record with Trello card data
        success = update_job_record_with_trello_data(job, card_data)
        if success:
            logger.info(f"Successfully updated database record with Trello data")
        else:
            logger.error(f"Failed to update database record with Trello data")
        
        # Apply post-creation features (Fab Order, FC Drawing, notes, mirror card)
        post_creation_results = apply_card_post_creation_features(
            card_id=card_id,
            list_id=list_id,
            job_record=job,
            notes=job.notes,  # Scanner also handles notes as comments
            create_mirror=True,  # Scanner creates mirror cards
            operation_id=None
        )
        
        return {
            "success": True,
            "card_id": card_id,
            "card_name": card_data.get('name', ''),
            "list_name": list_name,
            "job": job.job,
            "release": job.release,
            "mirror_card_id": post_creation_results.get("mirror_card_id")
        }
        
    except Exception as err:
        error_msg = f"Error creating Trello card for job {job.job}-{job.release}: {err}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "job": job.job,
            "release": job.release,
            "error": str(err)
        }


def sync_trello_with_db(dry_run: bool = False) -> Dict:
    """
    Sync Trello board with database:
    1. Delete Trello-only cards
    2. Move cards to correct lists based on DB stage
    3. Create cards for DB-only jobs
    
    Args:
        dry_run: If True, only report what would be done without making changes
        
    Returns:
        Dictionary with sync results
    """
    from app.trello.api import get_list_by_name, update_trello_card
    
    logger.info(f"Starting Trello-DB sync (dry_run={dry_run})")
    
    # Get comparison scan
    scan_results = scan_trello_db_comparison()
    
    if "error" in scan_results:
        return {
            "success": False,
            "error": scan_results["error"],
            "dry_run": dry_run
        }
    
    results = {
        "dry_run": dry_run,
        "deleted": {"success": [], "failed": []},
        "moved": {"success": [], "failed": []},
        "created": {"success": [], "failed": []},
        "summary": scan_results["summary"]
    }
    
    # 1. Delete Trello-only cards
    logger.info(f"Deleting {len(scan_results['trello_only'])} Trello-only cards...")
    for card_info in scan_results['trello_only']:
        card_id = card_info['trello_card_id']
        if dry_run:
            results["deleted"]["success"].append({
                "card_id": card_id,
                "card_name": card_info['trello_card_name'],
                "identifier": card_info['identifier']
            })
        else:
            delete_result = delete_trello_card(card_id)
            if delete_result["success"]:
                results["deleted"]["success"].append(delete_result)
            else:
                results["deleted"]["failed"].append(delete_result)
    
    # 2. Move cards to correct lists based on DB stage
    logger.info(f"Moving {len(scan_results['list_mismatches'])} cards to correct lists...")
    for mismatch in scan_results['list_mismatches']:
        card_id = mismatch['trello_card_id']
        expected_list = mismatch['expected_list']
        
        if not expected_list:
            logger.warning(f"Skipping card {card_id} - no expected list for stage '{mismatch['db_stage']}'")
            continue
        
        # Get list ID
        list_info = get_list_by_name(expected_list)
        if not list_info:
            error_msg = f"List '{expected_list}' not found"
            logger.error(error_msg)
            results["moved"]["failed"].append({
                "card_id": card_id,
                "identifier": mismatch['identifier'],
                "error": error_msg
            })
            continue
        
        if dry_run:
            results["moved"]["success"].append({
                "card_id": card_id,
                "identifier": mismatch['identifier'],
                "from_list": mismatch['trello_list'],
                "to_list": expected_list
            })
        else:
            try:
                update_trello_card(card_id, new_list_id=list_info['id'])
                
                # Update DB job record with new list info
                job = Job.query.filter_by(job=mismatch['job'], release=mismatch['release']).first()
                if job:
                    from app.trello.api import get_list_name_by_id
                    job.trello_list_id = list_info['id']
                    job.trello_list_name = expected_list
                    db.session.commit()
                    logger.info(f"Updated DB record for {mismatch['identifier']} with new list info")
                
                results["moved"]["success"].append({
                    "card_id": card_id,
                    "identifier": mismatch['identifier'],
                    "from_list": mismatch['trello_list'],
                    "to_list": expected_list
                })
                logger.info(f"Moved card {card_id} from '{mismatch['trello_list']}' to '{expected_list}'")
            except Exception as err:
                error_msg = str(err)
                logger.error(f"Error moving card {card_id}: {error_msg}")
                results["moved"]["failed"].append({
                    "card_id": card_id,
                    "identifier": mismatch['identifier'],
                    "error": error_msg
                })
    
    # 3. Create cards for DB-only jobs
    logger.info(f"Creating {len(scan_results['db_only'])} cards for DB-only jobs...")
    for job_info in scan_results['db_only']:
        # Get the job from database
        job = Job.query.filter_by(job=job_info['job'], release=job_info['release']).first()
        if not job:
            logger.warning(f"Job {job_info['identifier']} not found in database, skipping")
            continue
        
        if dry_run:
            expected_list = get_expected_trello_list_from_stage(job.stage) or "Released"
            results["created"]["success"].append({
                "job": job.job,
                "release": job.release,
                "identifier": job_info['identifier'],
                "expected_list": expected_list
            })
        else:
            create_result = create_trello_card_for_db_job(job)
            if create_result["success"]:
                results["created"]["success"].append(create_result)
            else:
                results["created"]["failed"].append(create_result)
    
    # Update summary
    results["summary"]["deleted_count"] = len(results["deleted"]["success"])
    results["summary"]["moved_count"] = len(results["moved"]["success"])
    results["summary"]["created_count"] = len(results["created"]["success"])
    results["summary"]["deleted_failed"] = len(results["deleted"]["failed"])
    results["summary"]["moved_failed"] = len(results["moved"]["failed"])
    results["summary"]["created_failed"] = len(results["created"]["failed"])
    
    logger.info(f"Sync complete: deleted={results['summary']['deleted_count']}, "
                f"moved={results['summary']['moved_count']}, "
                f"created={results['summary']['created_count']}")
    
    return results


def scan_and_create_cards_for_all_jobs(dry_run: bool = False, limit: Optional[int] = None) -> Dict:
    """
    Scan all jobs in the database and create Trello cards for jobs that don't have them.
    
    This function:
    - Queries all jobs from the database
    - Filters out jobs that already have trello_card_id (duplicates)
    - Determines the appropriate list for each job based on stage
    - Creates cards with all standard features (notes, fab order, FC drawing, num guys, etc.)
    - Works across all tracked lists
    
    Args:
        dry_run: If True, only report what would be created without making changes
        limit: Maximum number of jobs to process (None for all)
    
    Returns:
        Dictionary with scan and creation results
    """
    logger.info(f"Starting scan and create cards for all jobs (dry_run={dry_run})")
    
    try:
        # Query all jobs that don't have Trello cards
        query = Job.query.filter(Job.trello_card_id.is_(None))
        
        if limit:
            query = query.limit(limit)
        
        jobs_without_cards = query.all()
        
        logger.info(f"Found {len(jobs_without_cards)} jobs without Trello cards")
        
        if len(jobs_without_cards) == 0:
            return {
                "success": True,
                "total_jobs": 0,
                "created": 0,
                "failed": 0,
                "skipped": 0,
                "dry_run": dry_run,
                "created_details": [],
                "failed_details": []
            }
        
        results = {
            "success": True,
            "total_jobs": len(jobs_without_cards),
            "created": 0,
            "failed": 0,
            "skipped": 0,
            "dry_run": dry_run,
            "created_details": [],
            "failed_details": []
        }
        
        # Process each job
        for idx, job in enumerate(jobs_without_cards, 1):
            job_id = f"{job.job}-{job.release}"
            
            try:
                # Determine expected list from stage
                expected_list = get_expected_trello_list_from_stage(job.stage)
                if not expected_list:
                    expected_list = "Released"  # Default fallback
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would create card for {job_id} in list '{expected_list}'")
                    results["created"] += 1
                    results["created_details"].append({
                        "job": job.job,
                        "release": job.release,
                        "identifier": job_id,
                        "expected_list": expected_list,
                        "stage": job.stage
                    })
                else:
                    logger.info(f"[{idx}/{len(jobs_without_cards)}] Creating card for {job_id} in list '{expected_list}'")
                    
                    # Create card using the standard function (handles all features)
                    create_result = create_trello_card_for_db_job(job, list_name=expected_list)
                    
                    if create_result.get("success"):
                        results["created"] += 1
                        results["created_details"].append({
                            "job": job.job,
                            "release": job.release,
                            "identifier": job_id,
                            "card_id": create_result.get("card_id"),
                            "mirror_card_id": create_result.get("mirror_card_id"),
                            "list_name": create_result.get("list_name"),
                            "stage": job.stage
                        })
                        logger.info(f"Successfully created card for {job_id}")
                    else:
                        error = create_result.get("error", "Unknown error")
                        if "already exists" in error.lower():
                            results["skipped"] += 1
                            logger.info(f"Skipped {job_id}: {error}")
                        else:
                            results["failed"] += 1
                            results["failed_details"].append({
                                "job": job.job,
                                "release": job.release,
                                "identifier": job_id,
                                "error": error,
                                "stage": job.stage
                            })
                            logger.error(f"Failed to create card for {job_id}: {error}")
            
            except Exception as err:
                error_msg = str(err)
                logger.error(f"Error processing {job_id}: {error_msg}", exc_info=True)
                results["failed"] += 1
                results["failed_details"].append({
                    "job": job.job,
                    "release": job.release,
                    "identifier": job_id,
                    "error": error_msg,
                    "stage": job.stage if hasattr(job, 'stage') else None
                })
        
        logger.info(f"Scan and create complete: created={results['created']}, "
                   f"failed={results['failed']}, skipped={results['skipped']}")
        
        return results
        
    except Exception as e:
        error_msg = f"Scan and create failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "error_type": type(e).__name__,
            "dry_run": dry_run
        }

