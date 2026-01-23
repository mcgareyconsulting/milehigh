"""
Scheduling service for updating Job model records with calculated scheduling fields.

This service calculates and updates start_install and comp_eta fields in the database
based on the scheduling logic.
"""

from datetime import date, datetime
from typing import List, Optional
from app.models import Job, db
from app.brain.job_log.scheduling.calculator import calculate_all_job_scheduling
from app.logging_config import get_logger

logger = get_logger(__name__)


def update_job_scheduling_fields(
    job: Job,
    all_jobs: Optional[List[Job]] = None,
    reference_date: Optional[date] = None,
    commit: bool = True
) -> Job:
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
    if reference_date is None:
        reference_date = date.today()
    
    # Fetch all jobs if not provided (needed for hours_in_front calculation)
    if all_jobs is None:
        all_jobs = Job.query.all()
    
    # Convert Job models to dictionaries for calculation
    all_jobs_dicts = []
    for j in all_jobs:
        all_jobs_dicts.append({
            'fab_hrs': j.fab_hrs,
            'install_hrs': j.install_hrs,
            'fab_order': j.fab_order,
            'stage': j.stage if j.stage else 'Released',
        })
    
    # Convert current job to dict
    job_dict = {
        'fab_hrs': job.fab_hrs,
        'install_hrs': job.install_hrs,
        'fab_order': job.fab_order,
        'stage': job.stage if job.stage else 'Released',
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
            f"Updated scheduling for job {job.job}-{job.release}: "
            f"start_install={old_start_install}→{job.start_install}, "
            f"comp_eta={old_comp_eta}→{job.comp_eta}"
        )
    
    if commit:
        db.session.commit()
    
    return job


def recalculate_all_jobs_scheduling(
    reference_date: Optional[date] = None,
    batch_size: int = 100
) -> dict:
    """
    Recalculate and update scheduling fields for all jobs in the database.
    
    This function:
    1. Fetches all jobs from the database
    2. Calculates scheduling fields for all jobs
    3. Updates start_install and comp_eta fields
    4. Commits changes in batches
    
    Args:
        reference_date: Reference date for calculations (defaults to today)
        batch_size: Number of jobs to commit in each batch (default: 100)
        
    Returns:
        dict: Summary of updates with counts and any errors
    """
    if reference_date is None:
        reference_date = date.today()
    
    logger.info(f"Starting scheduling recalculation for all jobs (reference_date={reference_date})")
    
    # Fetch all jobs
    all_jobs = Job.query.all()
    total_jobs = len(all_jobs)
    
    if total_jobs == 0:
        logger.warning("No jobs found in database")
        return {
            'total_jobs': 0,
            'updated': 0,
            'errors': []
        }
    
    logger.info(f"Processing {total_jobs} jobs")
    
    # Convert to dictionaries for calculation
    jobs_dicts = []
    for job in all_jobs:
        jobs_dicts.append({
            'fab_hrs': job.fab_hrs,
            'install_hrs': job.install_hrs,
            'fab_order': job.fab_order,
            'stage': job.stage if job.stage else 'Released',
        })
    
    # Calculate scheduling for all jobs
    jobs_with_scheduling = calculate_all_job_scheduling(jobs_dicts, reference_date)
    
    # Update jobs in batches
    updated_count = 0
    errors = []
    
    for i, (job, scheduling) in enumerate(zip(all_jobs, jobs_with_scheduling)):
        try:
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
                logger.debug(f"Committed batch: {i + 1}/{total_jobs} jobs processed")
                
        except Exception as e:
            error_msg = f"Error updating job {job.job}-{job.release}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append({
                'job': f"{job.job}-{job.release}",
                'error': str(e)
            })
            # Continue with next job
    
    # Final commit for remaining jobs
    try:
        db.session.commit()
    except Exception as e:
        logger.error(f"Error in final commit: {str(e)}", exc_info=True)
        errors.append({
            'job': 'final_commit',
            'error': str(e)
        })
    
    logger.info(
        f"Scheduling recalculation complete: {updated_count}/{total_jobs} jobs updated, "
        f"{len(errors)} errors"
    )
    
    return {
        'total_jobs': total_jobs,
        'updated': updated_count,
        'errors': errors
    }

