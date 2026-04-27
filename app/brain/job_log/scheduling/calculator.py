"""
@milehigh-header
schema_version: 1
purpose: Implement the core scheduling pipeline (remaining hours, queue position, projected dates) matching legacy Excel formulas exactly.
exports:
  calculate_remaining_fab_hours: Remaining fab hours = total * stage percentage
  calculate_hours_in_front: Sum of remaining hours for all jobs ahead in queue
  calculate_days_in_front: Convert hours-in-front to working days (ROUNDUP)
  calculate_projected_fab_complete_date: Today + days_in_front business days
  calculate_install_start_date: Fab complete + buffer business days
  calculate_install_complete_date: Install start + ceil(install_hrs / capacity) business days
  calculate_scheduling_fields: Compute all scheduling fields for one job
  calculate_all_job_scheduling: Two-pass batch calculation for all jobs
imports_from: [app.brain.job_log.scheduling.config, app.trello.utils]
imported_by: [app/brain/job_log/scheduling/__init__.py, app/brain/job_log/scheduling/service.py, app/brain/job_log/scheduling/preview.py]
invariants:
  - Hard-date jobs (is_hard_date=True) are excluded from hours_in_front sums
  - All date arithmetic uses business days only (Monday-Friday)
  - Unknown stages default to 100% remaining (conservative)
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Scheduling calculation module.

This module implements the core scheduling logic exactly as specified,
matching Excel behavior for all calculations.
"""

import math
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple, Any

from app.brain.job_log.scheduling.config import SchedulingConfig
from app.trello.utils import add_business_days
from app.api.helpers import DEFAULT_FAB_ORDER


def _has_real_fab_order(fab_order: Optional[float]) -> bool:
    # DEFAULT_FAB_ORDER (80.555) is a sentinel for "no explicit fab_order assigned" — these
    # releases must still cascade, but should not contribute to or consume queue position.
    if fab_order is None:
        return False
    return fab_order != DEFAULT_FAB_ORDER


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
    if not _has_real_fab_order(job_fab_order):
        # Jobs without fab_order (or with the DEFAULT_FAB_ORDER sentinel) are considered at the
        # end of the queue. They still get cascaded dates based on every real-fab_order release
        # in front of them, but their order among themselves is left ambiguous.
        # Exclude hard-date jobs — they have fixed install dates and don't consume queue capacity.
        return sum(
            job.get('remaining_fab_hours', 0.0)
            for job in all_jobs
            if _has_real_fab_order(job.get('fab_order')) and not job.get('is_hard_date')
        )

    # Sum remaining hours for jobs with lower (earlier) fab_order.
    # Exclude hard-date jobs — they have fixed install dates and don't consume queue capacity.
    # Exclude sentinel-order jobs — they don't have a real queue position.
    hours_in_front = 0.0
    for job in all_jobs:
        other_fab_order = job.get('fab_order')
        if _has_real_fab_order(other_fab_order) and other_fab_order < job_fab_order and not job.get('is_hard_date'):
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
    
    if install_hours is None or install_hours < 0:
        return None

    if install_hours == 0:
        return install_start_date
    
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

