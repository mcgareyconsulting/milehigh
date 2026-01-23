"""
Scheduling calculation module.

This module implements the core scheduling logic exactly as specified,
matching Excel behavior for all calculations.
"""

import math
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple, Any

from app.brain.job_log.scheduling.config import SchedulingConfig
from app.trello.utils import add_business_days


def calculate_remaining_fab_hours(
    total_fab_hours: Optional[float],
    stage: Optional[str]
) -> float:
    """
    Calculate remaining fabrication hours for a job-release.
    
    Formula: remaining_fab_hours = total_fab_hours × stage_remaining_percentage
    
    Args:
        total_fab_hours: Total fabrication hours for the job-release
        stage: Current stage name
        
    Returns:
        float: Remaining fabrication hours (never negative)
    """
    if total_fab_hours is None or total_fab_hours <= 0:
        return 0.0
    
    # Get stage percentage from config
    stage_percentage = SchedulingConfig.get_stage_remaining_percentage(
        stage if stage else 'Released'
    )
    
    remaining = total_fab_hours * stage_percentage
    
    # Ensure never negative
    return max(0.0, remaining)


def calculate_hours_in_front(
    job_fab_order: Optional[float],
    all_jobs: List[Dict[str, Any]]
) -> float:
    """
    Calculate hours in front for a given job-release.
    
    Formula: sum of remaining_fab_hours for all job-releases with lower fab_order
    
    Args:
        job_fab_order: Fab order number for this job-release
        all_jobs: List of all job dictionaries with 'fab_order' and calculated 'remaining_fab_hours'
        
    Returns:
        float: Total hours in front (sum of remaining hours for jobs ahead in queue)
    """
    if job_fab_order is None:
        # Jobs without fab_order are considered at the end of the queue
        # They have all other jobs in front of them
        return sum(
            job.get('remaining_fab_hours', 0.0)
            for job in all_jobs
            if job.get('fab_order') is not None
        )
    
    # Sum remaining hours for jobs with lower (earlier) fab_order
    hours_in_front = 0.0
    for job in all_jobs:
        other_fab_order = job.get('fab_order')
        if other_fab_order is not None and other_fab_order < job_fab_order:
            hours_in_front += job.get('remaining_fab_hours', 0.0)
    
    return hours_in_front


def calculate_days_in_front(hours_in_front: float) -> int:
    """
    Convert hours in front to working days.
    
    Formula:
    - If hours_in_front ≤ 0.1 → days_in_front = 0
    - Otherwise → round UP to nearest whole day (Excel ROUNDUP behavior)
    
    Args:
        hours_in_front: Total hours in front
        
    Returns:
        int: Days in front (rounded up, minimum 0)
    """
    if hours_in_front <= 0.1:
        return 0
    
    # Round up to nearest whole day (Excel ROUNDUP behavior)
    fab_capacity = SchedulingConfig.FAB_HOURS_PER_DAY
    days = math.ceil(hours_in_front / fab_capacity)
    
    return max(0, days)


def calculate_projected_fab_complete_date(
    days_in_front: int,
    reference_date: Optional[date] = None
) -> Optional[date]:
    """
    Calculate projected fabrication completion date.
    
    Formula: today + days_in_front (working days only)
    
    If days_in_front = 0, returns reference_date (today).
    
    Args:
        days_in_front: Number of working days in front
        reference_date: Reference date (defaults to today)
        
    Returns:
        date: Projected fab completion date, or None if reference_date is None
    """
    if reference_date is None:
        reference_date = date.today()
    
    if days_in_front == 0:
        return reference_date
    
    # Add working days (Monday-Friday only)
    return add_business_days(reference_date, days_in_front)


def calculate_install_start_date(
    projected_fab_complete_date: Optional[date]
) -> Optional[date]:
    """
    Calculate install start date.
    
    Formula: projected_fab_completion + install_buffer (working days)
    
    Args:
        projected_fab_complete_date: Projected fab completion date
        
    Returns:
        date: Install start date, or None if projected_fab_complete_date is None
    """
    if projected_fab_complete_date is None:
        return None
    
    buffer_days = SchedulingConfig.INSTALL_BUFFER_DAYS
    return add_business_days(projected_fab_complete_date, buffer_days)


def calculate_install_complete_date(
    install_start_date: Optional[date],
    install_hours: Optional[float]
) -> Optional[date]:
    """
    Calculate install completion ETA.
    
    Formula:
    - Convert install hours → install days (round up)
    - Completion date = install start + install days (working days only)
    
    Args:
        install_start_date: Install start date
        install_hours: Installation hours for the job-release
        
    Returns:
        date: Install completion date, or None if install_hours is zero/null or start_date is None
    """
    if install_start_date is None:
        return None
    
    if install_hours is None or install_hours <= 0:
        return None
    
    # Convert install hours to days (round up)
    install_capacity = SchedulingConfig.INSTALL_HOURS_PER_DAY
    install_days = math.ceil(install_hours / install_capacity)
    
    if install_days <= 0:
        return None
    
    # Add working days
    return add_business_days(install_start_date, install_days)


def calculate_scheduling_fields(
    job: Dict[str, Any],
    all_jobs: List[Dict[str, Any]],
    reference_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Calculate all scheduling fields for a single job-release.
    
    This function computes all derived scheduling fields:
    - remaining_fab_hours
    - hours_in_front
    - days_in_front
    - projected_fab_complete_date
    - install_start_date
    - install_complete_date
    
    Args:
        job: Job dictionary with at least: fab_hrs, install_hrs, fab_order, stage
        all_jobs: List of all job dictionaries (for calculating hours_in_front)
        reference_date: Reference date for calculations (defaults to today)
        
    Returns:
        dict: Dictionary with all calculated scheduling fields
    """
    if reference_date is None:
        reference_date = date.today()
    
    # Extract job data
    total_fab_hours = job.get('fab_hrs')
    install_hours = job.get('install_hrs')
    fab_order = job.get('fab_order')
    stage = job.get('stage')
    
    # Step 1: Calculate remaining fab hours
    remaining_fab_hours = calculate_remaining_fab_hours(total_fab_hours, stage)
    
    # Step 2: Calculate hours in front (requires all jobs with remaining hours)
    # First, ensure all jobs have remaining_fab_hours calculated
    jobs_with_remaining = []
    for j in all_jobs:
        if 'remaining_fab_hours' not in j:
            j_remaining = calculate_remaining_fab_hours(
                j.get('fab_hrs'),
                j.get('stage')
            )
            jobs_with_remaining.append({**j, 'remaining_fab_hours': j_remaining})
        else:
            jobs_with_remaining.append(j)
    
    hours_in_front = calculate_hours_in_front(fab_order, jobs_with_remaining)
    
    # Step 3: Calculate days in front
    days_in_front = calculate_days_in_front(hours_in_front)
    
    # Step 4: Calculate projected fab completion date
    projected_fab_complete_date = calculate_projected_fab_complete_date(
        days_in_front,
        reference_date
    )
    
    # Step 5: Calculate install start date
    install_start_date = calculate_install_start_date(projected_fab_complete_date)
    
    # Step 6: Calculate install completion date
    install_complete_date = calculate_install_complete_date(
        install_start_date,
        install_hours
    )
    
    return {
        'remaining_fab_hours': remaining_fab_hours,
        'hours_in_front': hours_in_front,
        'days_in_front': days_in_front,
        'projected_fab_complete_date': projected_fab_complete_date,
        'install_start_date': install_start_date,
        'install_complete_date': install_complete_date,
    }


def calculate_all_job_scheduling(
    jobs: List[Dict[str, Any]],
    reference_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Calculate scheduling fields for all job-releases.
    
    This function processes all jobs and adds scheduling fields to each.
    Jobs must be processed together because hours_in_front depends on all other jobs.
    
    Args:
        jobs: List of job dictionaries with at least: fab_hrs, install_hrs, fab_order, stage
        reference_date: Reference date for calculations (defaults to today)
        
    Returns:
        list: List of job dictionaries with added scheduling fields
    """
    if reference_date is None:
        reference_date = date.today()
    
    # First pass: Calculate remaining_fab_hours for all jobs
    jobs_with_remaining = []
    for job in jobs:
        remaining = calculate_remaining_fab_hours(
            job.get('fab_hrs'),
            job.get('stage')
        )
        jobs_with_remaining.append({
            **job,
            'remaining_fab_hours': remaining
        })
    
    # Second pass: Calculate all scheduling fields for each job
    # (hours_in_front requires all jobs to have remaining_fab_hours)
    result = []
    for job in jobs_with_remaining:
        scheduling_fields = calculate_scheduling_fields(
            job,
            jobs_with_remaining,
            reference_date
        )
        result.append({
            **job,
            **scheduling_fields
        })
    
    return result

