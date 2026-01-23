"""
Preview script to show differences between current and computed scheduling dates.

This script calculates what the new start_install and comp_eta values would be
and shows a diff against the current database values, without making any changes.
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from app.models import Job, db
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
    
    logger.info(f"Previewing scheduling changes (reference_date={reference_date})")
    
    # Fetch all jobs
    all_jobs = Job.query.order_by(Job.job.asc(), Job.release.asc()).all()
    total_jobs = len(all_jobs)
    
    if total_jobs == 0:
        logger.warning("No jobs found in database")
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
    Print a formatted preview of scheduling changes.
    
    Args:
        preview_results: Results from preview_scheduling_changes()
        detailed: If True, show detailed diff for each job. If False, only show summary.
    """
    summary = preview_results.get('summary', {})
    jobs = preview_results.get('jobs', [])
    
    print("\n" + "=" * 80)
    print("SCHEDULING PREVIEW - Changes Summary")
    print("=" * 80)
    
    if summary:
        print(f"\nTotal Jobs: {summary.get('total_jobs', 0)}")
        print(f"Jobs with Changes: {summary.get('jobs_with_changes', 0)}")
        print(f"Jobs without Changes: {summary.get('jobs_without_changes', 0)}")
        print(f"Start Install Changes: {summary.get('start_install_changes', 0)}")
        print(f"Comp ETA Changes: {summary.get('comp_eta_changes', 0)}")
        print(f"Reference Date: {summary.get('reference_date', 'N/A')}")
    
    if not detailed or not jobs:
        print("\n" + "=" * 80)
        return
    
    print("\n" + "=" * 80)
    print("DETAILED CHANGES")
    print("=" * 80)
    
    for job_data in jobs:
        job_id = f"{job_data['job']}-{job_data['release']}"
        job_name = job_data.get('job_name', 'N/A')
        
        print(f"\nJob: {job_id} - {job_name}")
        print(f"  Fab Order: {job_data.get('fab_order', 'None')}")
        print(f"  Stage: {job_data.get('stage', 'Released')}")
        print(f"  Fab Hrs: {job_data.get('fab_hrs', 'None')}")
        print(f"  Install Hrs: {job_data.get('install_hrs', 'None')}")
        print(f"  Remaining Fab Hrs: {job_data.get('remaining_fab_hours', 0.0):.2f}")
        print(f"  Hours In Front: {job_data.get('hours_in_front', 0.0):.2f}")
        print(f"  Days In Front: {job_data.get('days_in_front', 0)}")
        
        projected_fab = job_data.get('projected_fab_complete_date')
        if projected_fab:
            print(f"  Projected Fab Complete: {format_date(projected_fab)}")
        
        # Start Install diff
        current_start = job_data.get('current_start_install')
        computed_start = job_data.get('computed_start_install')
        start_changed = job_data.get('start_install_changed', False)
        
        if start_changed:
            # Calculate days difference
            if current_start and computed_start:
                days_diff = (computed_start - current_start).days
                diff_str = f" ({days_diff:+d} days)" if days_diff != 0 else ""
            else:
                diff_str = ""
            print(f"  ⚠️  Start Install: {format_date(current_start)} → {format_date(computed_start)}{diff_str}")
        else:
            print(f"  ✓  Start Install: {format_date(current_start)} (no change)")
        
        # Comp ETA diff
        current_comp = job_data.get('current_comp_eta')
        computed_comp = job_data.get('computed_comp_eta')
        comp_changed = job_data.get('comp_eta_changed', False)
        
        if comp_changed:
            # Calculate days difference
            if current_comp and computed_comp:
                days_diff = (computed_comp - current_comp).days
                diff_str = f" ({days_diff:+d} days)" if days_diff != 0 else ""
            else:
                diff_str = ""
            print(f"  ⚠️  Comp ETA: {format_date(current_comp)} → {format_date(computed_comp)}{diff_str}")
        else:
            print(f"  ✓  Comp ETA: {format_date(current_comp)} (no change)")
    
    print("\n" + "=" * 80)


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
        except (ValueError, TypeError):
            print(f"Warning: Invalid reference_date '{reference_date_str}', using today")
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
        logger.error(f"Error in preview script: {e}", exc_info=True)
        print(f"\nError: {e}")
        raise

