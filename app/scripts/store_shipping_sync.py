"""
Utilities for syncing shipping status for cards in the
"Store at MHMW for shipping" Trello list.

Provides:
- A scan function that previews which jobs would be updated
- A run function that applies the updates (sets ship field to "ST")
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy import asc

from app.config import Config as cfg
from app.logging_config import get_logger
from app.models import Job, db
from app.sync.services.trello_list_mapper import TrelloListMapper
from app.trello.api import get_list_by_name


logger = get_logger(__name__)

TARGET_LIST_NAME = "Store at MHMW for shipping"


EXPECTED_STATUS = {
    "fitup_comp": "X",
    "welded": "X",
    "paint_comp": "X",
    "ship": "ST",
}


def _normalize_value(value: Optional[str]) -> str:
    """Normalize status values for comparison."""
    return (value or "").strip().upper()


def _fetch_trello_cards_in_target_list() -> List[Dict]:
    """Fetch all open cards currently in the target Trello list."""
    list_info = get_list_by_name(TARGET_LIST_NAME)
    if not list_info:
        logger.warning("Target Trello list not found", list_name=TARGET_LIST_NAME)
        return []

    url = f"https://api.trello.com/1/lists/{list_info['id']}/cards"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "filter": "open",
        "fields": "id,name,idList",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _build_job_snapshot(job: Job) -> Dict[str, str]:
    """Return a lightweight snapshot of a job for reporting purposes."""
    return {
        "job_release": f"{job.job}-{job.release}",
        "job_name": job.job_name,
        "trello_card_id": job.trello_card_id,
        "trello_list_name": job.trello_list_name,
        "ship": job.ship,
        "fitup_comp": job.fitup_comp,
        "welded": job.welded,
        "paint_comp": job.paint_comp,
        "source_of_update": job.source_of_update,
        "last_updated_at": job.last_updated_at.isoformat() if job.last_updated_at else None,
    }


def _evaluate_jobs(jobs: List[Job]) -> Tuple[List[Job], int, int]:
    """
    Determine which jobs need updates and track status mismatches.

    Returns a tuple of (needing_update, status_mismatches, already_correct_count).
    """
    needing_update: List[Job] = []
    status_mismatches = 0
    already_correct = 0

    for job in jobs:
        normalized = {
            "fitup_comp": _normalize_value(job.fitup_comp),
            "welded": _normalize_value(job.welded),
            "paint_comp": _normalize_value(job.paint_comp),
            "ship": _normalize_value(job.ship),
        }

        if normalized == EXPECTED_STATUS:
            already_correct += 1
            continue

        needing_update.append(job)

        if normalized["ship"] == EXPECTED_STATUS["ship"]:
            status_mismatches += 1

    return needing_update, status_mismatches, already_correct


def _compare_db_and_trello(
    jobs: List[Job], trello_cards: List[Dict]
) -> Dict[str, object]:
    """Compare database records with Trello cards and return discrepancy details."""
    trello_card_ids = {card.get("id") for card in trello_cards if card.get("id")}
    db_card_ids = {job.trello_card_id for job in jobs if job.trello_card_id}
    jobs_missing_card_id = [
        f"{job.job}-{job.release}" for job in jobs if not job.trello_card_id
    ]

    missing_in_db = sorted(trello_card_ids - db_card_ids)
    missing_in_trello = sorted(db_card_ids - trello_card_ids)

    count_match = len(jobs) == len(trello_cards)
    id_sets_match = (
        not missing_in_db and not missing_in_trello and not jobs_missing_card_id
    )

    return {
        "db_count": len(jobs),
        "trello_count": len(trello_cards),
        "count_match": count_match,
        "id_sets_match": id_sets_match,
        "missing_in_db": missing_in_db,
        "missing_in_trello": missing_in_trello,
        "jobs_missing_card_id": jobs_missing_card_id,
    }


def scan_store_shipping(return_json: bool = False, limit: Optional[int] = None):
    """
    Preview jobs whose Trello cards are in the target list and whose ship
    column is not currently set to "ST".
    """
    jobs = (
        Job.query.filter(Job.trello_list_name == TARGET_LIST_NAME)
        .order_by(asc(Job.job), asc(Job.release))
        .all()
    )
    total_in_list = len(jobs)

    trello_cards = _fetch_trello_cards_in_target_list()
    comparison = _compare_db_and_trello(jobs, trello_cards)

    needing_update, status_mismatches, already_correct = _evaluate_jobs(jobs)

    logger.info(
        "Scan completed for Store at MHMW shipping sync",
        total_in_list=total_in_list,
        trello_count=comparison["trello_count"],
        needing_update=len(needing_update),
        already_correct=already_correct,
        count_match=comparison["count_match"],
        id_sets_match=comparison["id_sets_match"],
    )

    sample_limit = limit if limit is not None else 25
    sample_jobs = [_build_job_snapshot(job) for job in needing_update[:sample_limit]]

    result = {
        "target_list": TARGET_LIST_NAME,
        "total_in_list": total_in_list,
        "trello_count": comparison["trello_count"],
        "limit_applied": limit is not None and limit != 0,
        "needs_update": len(needing_update),
        "already_correct": already_correct,
        "status_mismatches": status_mismatches,
        "sample_jobs": sample_jobs,
        "expected_status": EXPECTED_STATUS,
        "count_match": comparison["count_match"],
        "id_sets_match": comparison["id_sets_match"],
        "missing_in_db": comparison["missing_in_db"],
        "missing_in_trello": comparison["missing_in_trello"],
        "jobs_missing_card_id": comparison["jobs_missing_card_id"],
    }

    if return_json:
        return result

    print("=" * 60)
    print("Store at MHMW Shipping Sync - Scan Report")
    print("=" * 60)
    print(f"Target list: {TARGET_LIST_NAME}")
    print(f"Total cards in list: {total_in_list}")
    print(f"Trello reported cards: {comparison['trello_count']}")
    print(f"Counts match: {comparison['count_match']}")
    print(f"Card IDs match: {comparison['id_sets_match']}")
    print(f"Needs update: {len(needing_update)}")
    print(f"Already correct: {already_correct}")
    print(f"Status mismatches (non-ship issues): {status_mismatches}")
    if comparison["missing_in_db"]:
        print(f"Missing in DB ({len(comparison['missing_in_db'])}): {comparison['missing_in_db']}")
    if comparison["missing_in_trello"]:
        print(f"Missing in Trello ({len(comparison['missing_in_trello'])}): {comparison['missing_in_trello']}")
    if comparison["jobs_missing_card_id"]:
        print(
            "Jobs missing trello_card_id: "
            f"{', '.join(comparison['jobs_missing_card_id'])}"
        )
    print("-" * 60)
    if sample_jobs:
        print("Sample jobs needing update (up to 25):")
        for job in sample_jobs:
            print(
                f"  - {job['job_release']} (ship={job['ship']}, "
                f"fitup={job['fitup_comp']}, welded={job['welded']}, "
                f"paint={job['paint_comp']})"
            )
            print(f"    Expected status: {EXPECTED_STATUS}")
    else:
        print("No jobs require updates.")
    print("=" * 60)


def run_store_shipping_sync(
    return_json: bool = False,
    limit: Optional[int] = None,
    batch_size: int = 50,
):
    """
    Apply shipping updates for jobs in the target Trello list.

    Sets ship column to "ST" (and related fields) using TrelloListMapper.
    """
    jobs = (
        Job.query.filter(Job.trello_list_name == TARGET_LIST_NAME)
        .order_by(asc(Job.job), asc(Job.release))
        .all()
    )
    trello_cards = _fetch_trello_cards_in_target_list()
    comparison = _compare_db_and_trello(jobs, trello_cards)

    missing_in_db = comparison["missing_in_db"]
    missing_in_trello = comparison["missing_in_trello"]
    jobs_missing_card_id = comparison["jobs_missing_card_id"]

    if missing_in_trello or jobs_missing_card_id:
        mismatch_result = {
            "target_list": TARGET_LIST_NAME,
            "aborted": True,
            "reason": "Database and Trello list are out of sync",
            "comparison": comparison,
            "limit_applied": False,
            "updated_jobs": [],
            "skipped_jobs": [],
            "processed": 0,
            "updated": 0,
            "skipped": 0,
        }
        if return_json:
            return mismatch_result

        print("=" * 60)
        print("Store at MHMW Shipping Sync - ABORTED")
        print("=" * 60)
        print("Database and Trello counts/IDs do not match. No updates were made.")
        print(f"DB count: {comparison['db_count']}")
        print(f"Trello count: {comparison['trello_count']}")
        print(f"Counts match: {comparison['count_match']}")
        print(f"Card IDs match: {comparison['id_sets_match']}")
        if missing_in_db:
            print("Card IDs missing in DB:", missing_in_db)
        if missing_in_trello:
            print("Card IDs missing in Trello:", missing_in_trello)
        if jobs_missing_card_id:
            print(
                "Jobs missing trello_card_id: "
                f"{', '.join(comparison['jobs_missing_card_id'])}"
            )
        print("=" * 60)
        return

    if missing_in_db:
        logger.warning(
            "Proceeding with Store shipping sync while skipping cards missing in DB",
            missing_in_db=missing_in_db,
        )

    needing_update, status_mismatches, already_correct = _evaluate_jobs(jobs)

    if not needing_update:
        result = {
            "target_list": TARGET_LIST_NAME,
            "total_candidates": 0,
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "batch_size_used": batch_size,
            "limit_applied": limit is not None and limit != 0,
            "updated_jobs": [],
            "skipped_jobs": [],
            "comparison": comparison,
            "status_mismatches": status_mismatches,
            "already_correct": already_correct,
            "skipped_missing_in_db": missing_in_db,
        }
        if return_json:
            return result
        print("No jobs require updates.")
        return

    total_candidates = len(needing_update)

    if limit is not None and limit > 0:
        jobs_to_update = needing_update[:limit]
    else:
        jobs_to_update = needing_update

    updated_jobs: List[Dict[str, str]] = []
    skipped_jobs: List[Dict[str, str]] = []
    processed = 0
    updated = 0
    skipped = 0

    operation_id = f"store_shipping_sync_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    for job in jobs_to_update:
        processed += 1
        previous_state = {
            "fitup_comp": job.fitup_comp,
            "welded": job.welded,
            "paint_comp": job.paint_comp,
            "ship": job.ship,
        }

        try:
            TrelloListMapper.apply_trello_list_to_db(
                job, TARGET_LIST_NAME, operation_id=operation_id
            )
            job.last_updated_at = datetime.utcnow()
            job.source_of_update = "System"

            db.session.add(job)
            db.session.commit()

            updated += 1
            updated_jobs.append(
                {
                    "job_release": f"{job.job}-{job.release}",
                    "previous_status": previous_state,
                    "new_status": {
                        "fitup_comp": job.fitup_comp,
                        "welded": job.welded,
                        "paint_comp": job.paint_comp,
                        "ship": job.ship,
                    },
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to update job during Store at MHMW shipping sync",
                job_release=f"{job.job}-{job.release}",
                error=str(exc),
            )
            db.session.rollback()
            skipped += 1
            skipped_jobs.append(
                {
                    "job_release": f"{job.job}-{job.release}",
                    "error": str(exc),
                }
            )

    result = {
        "target_list": TARGET_LIST_NAME,
        "total_candidates": total_candidates,
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "batch_size_used": batch_size,
        "limit_applied": limit is not None and limit != 0,
        "updated_jobs": updated_jobs[:25],
        "skipped_jobs": skipped_jobs[:25],
        "operation_id": operation_id,
        "comparison": comparison,
        "status_mismatches": status_mismatches,
        "already_correct": already_correct,
        "limit_requested": limit,
        "skipped_missing_in_db": missing_in_db,
    }

    logger.info(
        "Completed Store at MHMW shipping sync",
        operation_id=operation_id,
        processed=processed,
        updated=updated,
        skipped=skipped,
        total_candidates=total_candidates,
    )

    if return_json:
        return result

    print("=" * 60)
    print("Store at MHMW Shipping Sync - Run Summary")
    print("=" * 60)
    print(f"Target list: {TARGET_LIST_NAME}")
    print(f"Total candidates: {total_candidates}")
    print(f"Processed (limit={limit or 'None'}): {processed}")
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print(f"Trello comparison: {comparison}")
    if status_mismatches:
        print(f"Status mismatches resolved (non-ship fields): {status_mismatches}")
    print(f"Already correct before sync: {already_correct}")
    if updated_jobs:
        print("\nUpdated jobs (up to 25):")
        for job_info in updated_jobs[:25]:
            prev = job_info["previous_status"]
            new = job_info["new_status"]
            print(f"  - {job_info['job_release']}")
            print(f"    Previous: {prev}")
            print(f"    New:      {new}")
    if skipped_jobs:
        print("\nSkipped jobs (up to 25):")
        for job_info in skipped_jobs[:25]:
            print(f"  - {job_info['job_release']}: {job_info['error']}")
    if missing_in_db:
        print("\nTrello cards skipped because they are missing in DB:")
        for card_id in missing_in_db:
            print(f"  - {card_id}")
    print("=" * 60)


