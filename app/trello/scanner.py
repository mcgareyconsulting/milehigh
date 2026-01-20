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
    from app.trello.api import (
        get_list_by_name, 
        update_job_record_with_trello_data,
        copy_trello_card,
        link_cards,
        card_has_link_to,
        update_trello_card
    )
    from app.config import Config as cfg
    import requests
    
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
        
        # Format card title
        job_name = job.job_name or 'Unknown Job'
        job_description = job.description or 'Unknown Description'
        card_title = f"{job.job}-{job.release} {job_name} {job_description}"
        
        # Format card description
        description_parts = []
        if job.description:
            description_parts.append(f"**Description:** {job.description}")
        if job.install_hrs:
            description_parts.append(f"**Install HRS:** {job.install_hrs}")
        if job.paint_color:
            description_parts.append(f"**Paint color:** {job.paint_color}")
        if job.pm and job.by:
            description_parts.append(f"**Team:** PM: {job.pm} / BY: {job.by}")
        if job.released:
            description_parts.append(f"**Released:** {job.released}")
        
        card_description = "\n".join(description_parts) if description_parts else ""
        
        # Create the card
        url = "https://api.trello.com/1/cards"
        payload = {
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
            "name": card_title,
            "desc": card_description,
            "idList": list_id,
            "pos": "top"
        }
        
        logger.info(f"Creating Trello card for job {job.job}-{job.release} in list '{list_name}'")
        response = requests.post(url, params=payload)
        response.raise_for_status()
        
        card_data = response.json()
        logger.info(f"Trello card created successfully: {card_data['id']}")
        
        # Update the job record with Trello card data
        success = update_job_record_with_trello_data(job, card_data)
        if success:
            logger.info(f"Successfully updated database record with Trello data")
        else:
            logger.error(f"Failed to update database record with Trello data")
        
        # Create mirror card in unassigned list if configured
        mirror_card_id = None
        if cfg.UNASSIGNED_CARDS_LIST_ID:
            try:
                # Check if card already has a link (to avoid duplicates)
                if not card_has_link_to(card_data['id']):
                    logger.info(f"Creating mirror card in unassigned list for {job.job}-{job.release}")
                    cloned = copy_trello_card(card_data['id'], cfg.UNASSIGNED_CARDS_LIST_ID, pos="bottom")
                    mirror_card_id = cloned["id"]
                    link_cards(card_data['id'], mirror_card_id)
                    # Clear due dates on both cards
                    update_trello_card(card_data['id'], clear_due_date=True)
                    update_trello_card(mirror_card_id, clear_due_date=True)
                    logger.info(f"Mirror card created and linked: {mirror_card_id}")
                else:
                    logger.info(f"Card {card_data['id']} already has a link, skipping mirror card creation")
            except Exception as mirror_err:
                logger.warning(f"Failed to create mirror card for {job.job}-{job.release}: {mirror_err}")
        else:
            logger.debug("UNASSIGNED_CARDS_LIST_ID not configured, skipping mirror card creation")
        
        return {
            "success": True,
            "card_id": card_data['id'],
            "card_name": card_data.get('name', ''),
            "list_name": list_name,
            "job": job.job,
            "release": job.release,
            "mirror_card_id": mirror_card_id
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

