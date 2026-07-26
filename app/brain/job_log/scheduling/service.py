"""
@milehigh-header
schema_version: 1
purpose: Persist computed scheduling dates (start_install, comp_eta) back to Job records, with single-job and batch-recalculation modes.
exports:
  update_job_scheduling_fields: Calculate and save scheduling dates for one job
  recalculate_all_jobs_scheduling: Batch recalculate and commit scheduling for all (or filtered) jobs
imports_from: [app.models, app.brain.job_log.scheduling.calculator, app.logging_config]
imported_by: [app/brain/job_log/routes.py, app/brain/job_log/features/fab_order/command.py]
invariants:
  - Hard-date jobs (start_install_formulaTF=False) are never overwritten
  - Batch commits every batch_size records to limit transaction size
  - NaN floats are converted to None before calculation to prevent int() errors
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Scheduling service for updating Job model records with calculated scheduling fields.

This service calculates and updates start_install and comp_eta fields in the database
based on the scheduling logic.
"""

import math
from datetime import date, datetime
from typing import List, Optional
from app.models import Releases, db
from app.brain.job_log.scheduling.calculator import calculate_all_job_scheduling
from app.logging_config import get_logger


def _safe_float(val):
    """Convert NaN floats to None to prevent downstream int() conversion errors."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

logger = get_logger(__name__)


def update_job_scheduling_fields(
    job: Releases,
    all_jobs: Optional[List[Releases]] = None,
    reference_date: Optional[date] = None,
    commit: bool = True
) -> Releases:
    """
    Calculate and update scheduling fields for a single Job record.
    
    Updates:
    - start_install: Calculated install start date
    - comp_eta: Calculated install completion date
    
    Args:
        job: Job model instance to update
        all_jobs: Optional list of all Job records for queue calculation.
                 If None, fetches all jobs from database.
        reference_date: Reference date for calculations (defaults to today)
        commit: Whether to commit the database transaction (default: True)
        
    Returns:
        Job: Updated job record
    """
    # Protect hard dates (red dates) — never overwrite user-set dates
    if job.start_install_formulaTF is False:
        logger.debug("scheduling_update_skipped_hard_date", job=job.job, release=job.release)
        return job

    if reference_date is None:
        reference_date = date.today()

    # Fetch all jobs if not provided (needed for hours_in_front calculation)
    if all_jobs is None:
        all_jobs = Releases.query.all()
    
    # Convert Job models to dictionaries for calculation
    all_jobs_dicts = []
    for j in all_jobs:
        all_jobs_dicts.append({
            'fab_hrs': _safe_float(j.fab_hrs),
            'install_hrs': _safe_float(j.install_hrs),
            'fab_order': _safe_float(j.fab_order),
            'stage': j.stage if j.stage else 'Released',
            'num_guys': _safe_float(j.num_guys),
            'is_hard_date': j.start_install_formulaTF is False,
        })

    # Convert current job to dict
    job_dict = {
        'fab_hrs': _safe_float(job.fab_hrs),
        'install_hrs': _safe_float(job.install_hrs),
        'fab_order': _safe_float(job.fab_order),
        'stage': job.stage if job.stage else 'Released',
        'num_guys': _safe_float(job.num_guys),
        'is_hard_date': job.start_install_formulaTF is False,
    }
    
    # Calculate scheduling fields
    from app.brain.job_log.scheduling.calculator import calculate_scheduling_fields
    scheduling = calculate_scheduling_fields(job_dict, all_jobs_dicts, reference_date)
    
    # Update job record with calculated dates
    old_start_install = job.start_install
    old_comp_eta = job.comp_eta
    
    job.start_install = scheduling.get('install_start_date')
    job.comp_eta = scheduling.get('install_complete_date')
    
    # Update metadata
    job.last_updated_at = datetime.utcnow()
    if job.source_of_update != 'System':
        # Preserve original source unless it's already System
        job.source_of_update = job.source_of_update or 'System'
    
    # Log changes
    if old_start_install != job.start_install or old_comp_eta != job.comp_eta:
        logger.info(
            "scheduling_updated",
            job=job.job,
            release=job.release,
            from_start_install=old_start_install,
            to_start_install=job.start_install,
            from_comp_eta=old_comp_eta,
            to_comp_eta=job.comp_eta,
        )
    
    if commit:
        db.session.commit()
    
    return job


def recalculate_all_jobs_scheduling(
    reference_date: Optional[date] = None,
    batch_size: int = 100,
    stage_group: Optional[str] = None
) -> dict:
    """
    Recalculate and update scheduling fields for jobs in the database.

    This function:
    1. Fetches jobs from the database (optionally filtered by stage_group)
    2. Calculates scheduling fields for those jobs
    3. Updates start_install and comp_eta fields
    4. Commits changes in batches

    Args:
        reference_date: Reference date for calculations (defaults to today)
        batch_size: Number of jobs to commit in each batch (default: 100)
        stage_group: If set, only recalculate jobs in this stage group (e.g. 'FABRICATION')

    Returns:
        dict: Summary of updates with counts and any errors
    """
    if reference_date is None:
        reference_date = date.today()

    logger.debug(
        "scheduling_recalculation_started",
        stage_group=stage_group,
        reference_date=reference_date.isoformat(),
    )

    # Fetch jobs (filtered by stage_group if specified)
    query = Releases.query
    if stage_group:
        query = query.filter(Releases.stage_group == stage_group)
    all_jobs = query.all()

    # Cascade tiebreaker: rows with equal fab_order (notably the many DEFAULT_FAB_ORDER
    # 80.555 placeholders) must cascade chronologically by start_install. The calculator
    # already breaks fab_order ties by list position, so we encode the desired order here.
    # fab_order remains the primary key, so distinct-fab_order rows are unaffected.
    def _cascade_sort_key(j):
        fab_order = _safe_float(j.fab_order)
        return (
            fab_order if fab_order is not None else float('inf'),
            j.start_install or date.max,
        )

    all_jobs.sort(key=_cascade_sort_key)
    total_jobs = len(all_jobs)
    
    if total_jobs == 0:
        logger.debug("scheduling_recalculation_no_jobs", stage_group=stage_group, count=0)
        return {
            'total_jobs': 0,
            'updated': 0,
            'errors': []
        }
    
    logger.debug("scheduling_recalculation_jobs_loaded", count=total_jobs)
    
    # Convert to dictionaries for calculation
    jobs_dicts = []
    for job in all_jobs:
        jobs_dicts.append({
            'fab_hrs': _safe_float(job.fab_hrs),
            'install_hrs': _safe_float(job.install_hrs),
            'fab_order': _safe_float(job.fab_order),
            'stage': job.stage if job.stage else 'Released',
            'num_guys': _safe_float(job.num_guys),
            'is_hard_date': job.start_install_formulaTF is False,
        })
    
    # Calculate scheduling for all jobs
    jobs_with_scheduling = calculate_all_job_scheduling(jobs_dicts, reference_date)
    
    # Update jobs in batches
    updated_count = 0
    errors = []
    
    for i, (job, scheduling) in enumerate(zip(all_jobs, jobs_with_scheduling)):
        try:
            # Skip hard-date releases — their dates are user-set and must not be overwritten
            if job.start_install_formulaTF is False:
                continue

            old_start_install = job.start_install
            old_comp_eta = job.comp_eta

            # Update calculated fields
            job.start_install = scheduling.get('install_start_date')
            job.comp_eta = scheduling.get('install_complete_date')
            job.last_updated_at = datetime.utcnow()
            if job.source_of_update != 'System':
                job.source_of_update = job.source_of_update or 'System'
            
            # Track if anything changed
            if old_start_install != job.start_install or old_comp_eta != job.comp_eta:
                updated_count += 1
            
            # Commit in batches
            if (i + 1) % batch_size == 0:
                db.session.commit()
                logger.debug("scheduling_batch_committed", count=i + 1, total_jobs=total_jobs)
                
        except Exception as e:
            logger.error(
                "scheduling_job_update_failed",
                job=job.job,
                release=job.release,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            errors.append({
                'job': f"{job.job}-{job.release}",
                'error': str(e)
            })
            # Continue with next job
    
    # Final commit for remaining jobs
    try:
        db.session.commit()
    except Exception as e:
        logger.error(
            "scheduling_final_commit_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        errors.append({
            'job': 'final_commit',
            'error': str(e)
        })
    
    logger.info(
        "scheduling_recalculation_complete",
        total_jobs=total_jobs,
        updated=updated_count,
        error_count=len(errors),
        stage_group=stage_group,
    )
    
    return {
        'total_jobs': total_jobs,
        'updated': updated_count,
        'errors': errors
    }

