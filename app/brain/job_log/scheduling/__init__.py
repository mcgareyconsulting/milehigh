"""
@milehigh-header
schema_version: 1
purpose: Re-export all public scheduling symbols so callers can import from the package root instead of individual submodules.
exports:
  SchedulingConfig: Frozen scheduling parameters matching Excel behavior
  get_fab_modifier: Stage-to-remaining-work multiplier lookup
  calculate_total_fab_hrs: Sum remaining fab hours across jobs
  calculate_total_install_hrs: Sum remaining install hours for post-fab jobs
  calculate_scheduling_fields: Compute all scheduling dates for one job
  calculate_all_job_scheduling: Batch-compute scheduling for all jobs
imports_from: [app.brain.job_log.scheduling.config, app.brain.job_log.scheduling.hours_summary, app.brain.job_log.scheduling.calculator]
imported_by: [app/brain/job_log/routes.py, app/api/helpers.py]
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Scheduling logic module for job-release scheduling calculations.

This module implements the Excel-based scheduling logic in Python,
preserving all current scheduling assumptions until real stage-duration data is collected.
"""

from app.brain.job_log.scheduling.config import SchedulingConfig
from app.brain.job_log.scheduling.hours_summary import (
    get_fab_modifier,
    calculate_total_fab_hrs,
    calculate_total_install_hrs,
)
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
    'get_fab_modifier',
    'calculate_total_fab_hrs',
    'calculate_total_install_hrs',
    'calculate_remaining_fab_hours',
    'calculate_hours_in_front',
    'calculate_days_in_front',
    'calculate_projected_fab_complete_date',
    'calculate_install_start_date',
    'calculate_install_complete_date',
    'calculate_scheduling_fields',
    'calculate_all_job_scheduling',
]

