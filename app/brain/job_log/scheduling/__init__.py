"""
Scheduling logic module for job-release scheduling calculations.

This module implements the Excel-based scheduling logic in Python,
preserving all current scheduling assumptions until real stage-duration data is collected.
"""

from app.brain.job_log.scheduling.config import SchedulingConfig
from app.brain.job_log.scheduling.calculator import (
    calculate_remaining_fab_hours,
    calculate_hours_in_front,
    calculate_days_in_front,
    calculate_projected_fab_complete_date,
    calculate_install_start_date,
    calculate_install_complete_date,
    calculate_scheduling_fields,
    calculate_all_job_scheduling,
)

__all__ = [
    'SchedulingConfig',
    'calculate_remaining_fab_hours',
    'calculate_hours_in_front',
    'calculate_days_in_front',
    'calculate_projected_fab_complete_date',
    'calculate_install_start_date',
    'calculate_install_complete_date',
    'calculate_scheduling_fields',
    'calculate_all_job_scheduling',
]

