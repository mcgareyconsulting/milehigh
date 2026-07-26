"""
@milehigh-header
schema_version: 1
purpose: Generate a read-only diff of current vs. computed scheduling dates so admins can review before applying recalculation.
exports:
  preview_scheduling_changes: Compare DB dates against computed values, return structured diff
  print_preview: Emit the diff as structured debug log events
  run_preview_script: CLI entry point for running the preview
imports_from: [app.models, app.brain.job_log.scheduling.calculator, app.logging_config]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - Never writes to the database
  - show_all=False filters to only jobs with date changes
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Preview script to show differences between current and computed scheduling dates.

This script calculates what the new start_install and comp_eta values would be
and shows a diff against the current database values, without making any changes.
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from app.models import Releases, db
from app.brain.job_log.scheduling.calculator import calculate_all_job_scheduling
from app.logging_config import get_logger

logger = get_logger(__name__)


def format_date(d: Optional[date]) -> str:
    """Format a date for display, or 'None' if None."""
    if d is None:
        return 'None'
    return d.isoformat()


def preview_scheduling_changes(
    reference_date: Optional[date] = None,
    show_all: bool = False,
    show_summary: bool = True
) -> Dict[str, Any]:
    """
    Preview scheduling changes without updating the database.
    
    Args:
        reference_date: Reference date for calculations (defaults to today)
        show_all: If True, show all jobs. If False, only show jobs with changes.
        show_summary: If True, include summary statistics in output
        
    Returns:
        dict: Preview results with jobs list and summary
    """
    if reference_date is None:
        reference_date = date.today()
    
    logger.debug(
        "scheduling_preview_started",
        reference_date=reference_date.isoformat(),
        show_all=show_all,
    )
    
    # Fetch all jobs
    all_jobs = Releases.query.order_by(Releases.job.asc(), Releases.release.asc()).all()
    total_jobs = len(all_jobs)
    
    if total_jobs == 0:
        logger.debug("scheduling_preview_no_jobs", count=0)
        return {
            'total_jobs': 0,
            'jobs_with_changes': 0,
            'jobs': [],
            'summary': {}
        }
    
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
    
    # Compare current vs computed values
    preview_results = []
    jobs_with_changes = 0
    start_install_changes = 0
    comp_eta_changes = 0
    
    for job, scheduling in zip(all_jobs, jobs_with_scheduling):
        current_start_install = job.start_install
        current_comp_eta = job.comp_eta
        
        computed_start_install = scheduling.get('install_start_date')
        computed_comp_eta = scheduling.get('install_complete_date')
        
        # Check if there are changes
        start_changed = current_start_install != computed_start_install
        comp_changed = current_comp_eta != computed_comp_eta
        has_changes = start_changed or comp_changed
        
        if has_changes:
            jobs_with_changes += 1
            if start_changed:
                start_install_changes += 1
            if comp_changed:
                comp_eta_changes += 1
        
        # Include in results if show_all is True or if there are changes
        if show_all or has_changes:
            preview_results.append({
                'job': job.job,
                'release': job.release,
                'job_name': job.job_name,
                'fab_order': job.fab_order,
                'stage': job.stage if job.stage else 'Released',
                'fab_hrs': job.fab_hrs,
                'install_hrs': job.install_hrs,
                'current_start_install': current_start_install,
                'computed_start_install': computed_start_install,
                'start_install_changed': start_changed,
                'current_comp_eta': current_comp_eta,
                'computed_comp_eta': computed_comp_eta,
                'comp_eta_changed': comp_changed,
                'remaining_fab_hours': scheduling.get('remaining_fab_hours', 0.0),
                'hours_in_front': scheduling.get('hours_in_front', 0.0),
                'days_in_front': scheduling.get('days_in_front', 0),
                'projected_fab_complete_date': scheduling.get('projected_fab_complete_date'),
            })
    
    summary = {
        'total_jobs': total_jobs,
        'jobs_with_changes': jobs_with_changes,
        'jobs_without_changes': total_jobs - jobs_with_changes,
        'start_install_changes': start_install_changes,
        'comp_eta_changes': comp_eta_changes,
        'reference_date': reference_date.isoformat(),
    } if show_summary else {}
    
    return {
        'total_jobs': total_jobs,
        'jobs_with_changes': jobs_with_changes,
        'jobs': preview_results,
        'summary': summary
    }


def print_preview(preview_results: Dict[str, Any], detailed: bool = True):
    """
    Emit a structured debug trace of scheduling changes.

    Args:
        preview_results: Results from preview_scheduling_changes()
        detailed: If True, emit a detailed diff event for each job. If False, only emit the summary.
    """
    summary = preview_results.get('summary', {})
    jobs = preview_results.get('jobs', [])

    if summary:
        logger.debug(
            "scheduling_preview_summary",
            total_jobs=summary.get('total_jobs', 0),
            jobs_with_changes=summary.get('jobs_with_changes', 0),
            jobs_without_changes=summary.get('jobs_without_changes', 0),
            start_install_changes=summary.get('start_install_changes', 0),
            comp_eta_changes=summary.get('comp_eta_changes', 0),
            reference_date=summary.get('reference_date', 'N/A'),
        )

    if not detailed or not jobs:
        return

    for job_data in jobs:
        # Start Install diff
        current_start = job_data.get('current_start_install')
        computed_start = job_data.get('computed_start_install')
        start_changed = job_data.get('start_install_changed', False)

        start_days_diff = None
        if start_changed and current_start and computed_start:
            start_days_diff = (computed_start - current_start).days

        # Comp ETA diff
        current_comp = job_data.get('current_comp_eta')
        computed_comp = job_data.get('computed_comp_eta')
        comp_changed = job_data.get('comp_eta_changed', False)

        comp_days_diff = None
        if comp_changed and current_comp and computed_comp:
            comp_days_diff = (computed_comp - current_comp).days

        logger.debug(
            "scheduling_preview_job_diff",
            job=job_data['job'],
            release=job_data['release'],
            job_name=job_data.get('job_name', 'N/A'),
            fab_order=job_data.get('fab_order'),
            stage=job_data.get('stage', 'Released'),
            fab_hrs=job_data.get('fab_hrs'),
            install_hrs=job_data.get('install_hrs'),
            remaining_fab_hours=job_data.get('remaining_fab_hours', 0.0),
            hours_in_front=job_data.get('hours_in_front', 0.0),
            days_in_front=job_data.get('days_in_front', 0),
            projected_fab_complete_date=format_date(job_data.get('projected_fab_complete_date')),
            current_start_install=format_date(current_start),
            computed_start_install=format_date(computed_start),
            start_install_changed=start_changed,
            start_install_days_diff=start_days_diff,
            current_comp_eta=format_date(current_comp),
            computed_comp_eta=format_date(computed_comp),
            comp_eta_changed=comp_changed,
            comp_eta_days_diff=comp_days_diff,
        )


def run_preview_script(
    reference_date_str: Optional[str] = None,
    show_all: bool = False,
    detailed: bool = True
):
    """
    Run the preview script from command line.
    
    Args:
        reference_date_str: Optional ISO date string (YYYY-MM-DD)
        show_all: Show all jobs, not just those with changes
        detailed: Show detailed diff for each job
    """
    reference_date = None
    if reference_date_str:
        try:
            reference_date = datetime.fromisoformat(reference_date_str).date()
        except (ValueError, TypeError) as e:
            logger.error(
                "scheduling_preview_invalid_reference_date",
                reference_date_str=reference_date_str,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            reference_date = None
    
    try:
        preview_results = preview_scheduling_changes(
            reference_date=reference_date,
            show_all=show_all,
            show_summary=True
        )
        
        print_preview(preview_results, detailed=detailed)
        
        return preview_results
        
    except Exception as e:
        logger.error(
            "scheduling_preview_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise

