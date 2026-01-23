"""
Helper functions for transforming job data for API responses.
"""
from typing import Dict, Any, Union, List, Optional
from datetime import date
from app.models import Job


def determine_stage_from_db_fields(job: Union[Job, Any]) -> str:
    """
    Get the stage from the job's stage field.
    Returns the stage name or 'Released' if the stage field is None/empty.
    
    Args:
        job: Job model instance or object with stage attribute
    """
    # Use stage field directly from database
    if hasattr(job, 'stage') and job.stage:
        return job.stage
    return 'Released'


def determine_stage_from_job_dict(job_dict: Dict[str, Any]) -> str:
    """
    Get stage from a job dictionary (used when we have dict instead of Job object).
    This is a helper for transform_job_for_display.
    """
    # Get stage directly from dictionary, default to 'Released' if None/empty
    stage = job_dict.get('stage')
    return stage if stage else 'Released'


def transform_job_for_display(job_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform raw job data (from to_dict()) into display format.
    
    This includes:
    - Getting Stage from the stage field
    - Formatting dates to ISO strings
    - Mapping field names to display names
    - Excluding internal fields if needed
    """
    # Create a copy to avoid modifying the original
    transformed = {}
    
    # Map basic fields with display names
    transformed['id'] = job_dict.get('id')
    transformed['Job #'] = job_dict.get('job')
    transformed['Release #'] = job_dict.get('release')
    transformed['Job'] = job_dict.get('job_name')
    transformed['Description'] = job_dict.get('description')
    transformed['Fab Hrs'] = job_dict.get('fab_hrs')
    transformed['Install HRS'] = job_dict.get('install_hrs')
    transformed['Paint color'] = job_dict.get('paint_color')
    transformed['PM'] = job_dict.get('pm')
    transformed['BY'] = job_dict.get('by')
    
    # Format dates to ISO strings
    released = job_dict.get('released')
    transformed['Released'] = released.isoformat() if released else None
    
    transformed['Fab Order'] = job_dict.get('fab_order')
    
    # Get Stage from the stage field
    stage = determine_stage_from_job_dict(job_dict)
    transformed['Stage'] = stage
    
    # Format remaining dates
    start_install = job_dict.get('start_install')
    transformed['Start install'] = start_install.isoformat() if start_install else None
    
    comp_eta = job_dict.get('comp_eta')
    transformed['Comp. ETA'] = comp_eta.isoformat() if comp_eta else None
    
    transformed['Job Comp'] = job_dict.get('job_comp')
    transformed['Invoiced'] = job_dict.get('invoiced')
    transformed['Notes'] = job_dict.get('notes')
    
    return transformed


def add_scheduling_fields_to_jobs(
    jobs: List[Dict[str, Any]],
    all_jobs_for_queue: Optional[List[Dict[str, Any]]] = None,
    reference_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Add scheduling calculation fields to a list of job dictionaries.
    
    This function calculates all scheduling-derived fields for each job:
    - remaining_fab_hours
    - hours_in_front
    - days_in_front
    - projected_fab_complete_date
    - install_start_date
    - install_complete_date
    
    Note: hours_in_front depends on ALL jobs in the queue, not just the ones
    being returned. If all_jobs_for_queue is provided, it will be used for
    the queue calculation. Otherwise, only the provided jobs list is used.
    
    Args:
        jobs: List of job dictionaries to add scheduling fields to
        all_jobs_for_queue: Optional list of ALL jobs in the database for queue calculation.
                           If None, uses the jobs list (may be incomplete for paginated results)
        reference_date: Reference date for calculations (defaults to today)
        
    Returns:
        list: List of job dictionaries with added scheduling fields
    """
    from app.brain.job_log.scheduling import calculate_all_job_scheduling
    
    if not jobs:
        return jobs
    
    # Use all_jobs_for_queue if provided, otherwise use jobs
    queue_jobs = all_jobs_for_queue if all_jobs_for_queue is not None else jobs
    
    # Convert queue jobs to format expected by scheduling calculator
    queue_job_dicts = []
    for job in queue_jobs:
        job_dict = {
            'fab_hrs': job.get('Fab Hrs') or job.get('fab_hrs'),
            'install_hrs': job.get('Install HRS') or job.get('install_hrs'),
            'fab_order': job.get('Fab Order') or job.get('fab_order'),
            'stage': job.get('Stage') or job.get('stage'),
        }
        queue_job_dicts.append(job_dict)
    
    # Calculate scheduling for all queue jobs
    queue_jobs_with_scheduling = calculate_all_job_scheduling(queue_job_dicts, reference_date)
    
    # Create a lookup map by (fab_order, stage, fab_hrs) for matching
    # This handles cases where the returned jobs list is a subset
    scheduling_lookup = {}
    for i, queue_job in enumerate(queue_jobs):
        key = (
            queue_job.get('Fab Order') or queue_job.get('fab_order'),
            queue_job.get('Stage') or queue_job.get('stage'),
            queue_job.get('Fab Hrs') or queue_job.get('fab_hrs')
        )
        scheduling_lookup[key] = queue_jobs_with_scheduling[i]
    
    # Add scheduling fields to original job dictionaries
    result = []
    for job in jobs:
        # Find matching scheduling data
        job_key = (
            job.get('Fab Order') or job.get('fab_order'),
            job.get('Stage') or job.get('stage'),
            job.get('Fab Hrs') or job.get('fab_hrs')
        )
        
        scheduling = scheduling_lookup.get(job_key)
        if not scheduling:
            # Fallback: calculate for this job individually if not found in queue
            job_dict = {
                'fab_hrs': job.get('Fab Hrs') or job.get('fab_hrs'),
                'install_hrs': job.get('Install HRS') or job.get('install_hrs'),
                'fab_order': job.get('Fab Order') or job.get('fab_order'),
                'stage': job.get('Stage') or job.get('stage'),
            }
            from app.brain.job_log.scheduling import calculate_scheduling_fields
            scheduling = calculate_scheduling_fields(job_dict, queue_job_dicts, reference_date)
        
        # Add scheduling fields with display-friendly names
        job_with_scheduling = {**job}
        job_with_scheduling['remaining_fab_hours'] = scheduling.get('remaining_fab_hours', 0.0)
        job_with_scheduling['hours_in_front'] = scheduling.get('hours_in_front', 0.0)
        job_with_scheduling['days_in_front'] = scheduling.get('days_in_front', 0)
        
        # Format dates as ISO strings
        projected_fab_complete = scheduling.get('projected_fab_complete_date')
        job_with_scheduling['projected_fab_complete_date'] = (
            projected_fab_complete.isoformat() if projected_fab_complete else None
        )
        
        install_start = scheduling.get('install_start_date')
        job_with_scheduling['install_start_date'] = (
            install_start.isoformat() if install_start else None
        )
        
        install_complete = scheduling.get('install_complete_date')
        job_with_scheduling['install_complete_date'] = (
            install_complete.isoformat() if install_complete else None
        )
        
        result.append(job_with_scheduling)
    
    return result

