"""
Helper functions for transforming job data for API responses.
"""
from typing import Dict, Any, Union, List, Optional
from datetime import date
from app.models import Releases

# Stage to stage_group mapping
# Includes both user-provided names and actual stage names used in the codebase
STAGE_TO_GROUP = {
    # FABRICATION group
    "Released": "FABRICATION",
    "Cut Start": "FABRICATION",
    "Cut start": "FABRICATION",  # Actual name used in codebase
    "Fitup Complete": "FABRICATION",
    "Fit Up Complete.": "FABRICATION",  # Actual name used in codebase
    "Hold": "FABRICATION",  # Job log only stage
    "Material Ordered": "FABRICATION",  # Job log only stage
    "Welded": "FABRICATION",  # Job log only stage

    
    # READY_TO_SHIP group
    "Welded QC": "READY_TO_SHIP",
    "Paint Start": "READY_TO_SHIP",
    "Paint Complete": "READY_TO_SHIP",
    "Paint complete": "READY_TO_SHIP",  # Actual name used in codebase
    "Store at Shop": "READY_TO_SHIP",
    "Store at MHMW for shipping": "READY_TO_SHIP",  # Actual name used in codebase
    "Shipping Planning": "READY_TO_SHIP",
    "Shipping planning": "READY_TO_SHIP",  # Actual name used in codebase

    
    # COMPLETE group
    "Shipping Complete": "COMPLETE",
    "Shipping completed": "COMPLETE",  # Actual name used in codebase
    "Complete": "COMPLETE",
}

# Default fab_order for newly created releases when no value is provided
DEFAULT_FAB_ORDER = 80.555

# Fixed tiers: stages auto-assigned to a shared fab_order value (not user-orderable)
FIXED_TIER_STAGES = {
    1: ["Shipping completed", "Shipping Complete", "Complete"],
    2: ["Paint complete", "Paint Complete", "Store at MHMW for shipping", "Store at Shop", "Shipping planning", "Shipping Planning"],
}

# Dynamic stages ordered by priority (lower index = lower fab_order = closer to completion)
# fab_order 3+ is assigned sequentially within each stage block
DYNAMIC_STAGE_ORDER = [
    "Welded QC",
    "Paint Start",
    "Welded",
    "Fit Up Complete.",
    "Material Ordered",
    "Cut start",
    "Released",
]

# Legacy compat: kept for any code referencing STAGE_ORDER
STAGE_ORDER = {
    "FABRICATION": [
        "Released",
        "Cut start",
        "Material Ordered",
        "Fit Up Complete.",
        "Welded",
    ],
    "READY_TO_SHIP": [
        "Welded QC",
        "Paint Start",
        "Paint complete",
        "Store at MHMW for shipping",
        "Shipping planning",
    ],
}

STAGE_ORDER_EXEMPT = {"Hold"}


def _normalize_stage(stage: Optional[str]) -> Optional[str]:
    """Resolve a stage name (including variants) to the canonical key in STAGE_TO_GROUP."""
    if not stage:
        return None
    if stage in STAGE_TO_GROUP:
        return stage
    stage_lower = stage.lower()
    for key in STAGE_TO_GROUP:
        if key.lower() == stage_lower:
            return key
    return None


def _get_all_variants_for_stages(canonical_stages: List[str]) -> List[str]:
    """Given canonical stage names, return all variant strings from STAGE_TO_GROUP that match."""
    result = []
    canonical_lower = {s.lower() for s in canonical_stages}
    for variant in STAGE_TO_GROUP:
        if variant.lower() in canonical_lower:
            result.append(variant)
    return result


def get_stage_position(stage: Optional[str]) -> Optional[int]:
    """Return 0-based index of a stage in DYNAMIC_STAGE_ORDER, or None if exempt/fixed-tier."""
    normalized = _normalize_stage(stage)
    if normalized is None or normalized in STAGE_ORDER_EXEMPT:
        return None
    # Fixed-tier stages are not in the dynamic order
    if get_fixed_tier(normalized) is not None:
        return None
    normalized_lower = normalized.lower()
    for i, s in enumerate(DYNAMIC_STAGE_ORDER):
        if s.lower() == normalized_lower:
            return i
    return None


def get_fixed_tier(stage: Optional[str]) -> Optional[int]:
    """Return the fixed tier value (1 or 2) for a stage, or None if it's a dynamic stage."""
    if not stage:
        return None
    stage_lower = stage.lower()
    for tier, stages in FIXED_TIER_STAGES.items():
        for s in stages:
            if s.lower() == stage_lower:
                return tier
    return None


def get_fab_order_bounds(stage: Optional[str], current_job_id: int, current_release: str):
    """
    Return (lower_bound, upper_bound) fab_order constraints for a job's stage.

    Uses the unified DYNAMIC_STAGE_ORDER (not per-group).
    lower_bound = MAX fab_order of jobs in earlier dynamic stages
    upper_bound = MIN fab_order of jobs in later dynamic stages
    Returns (None, None) for Hold, fixed-tier, or unrecognized stages.
    """
    from sqlalchemy import func, or_
    from app.models import Releases, db

    normalized = _normalize_stage(stage)
    if normalized is None or normalized in STAGE_ORDER_EXEMPT:
        return (None, None)

    # Fixed-tier stages don't participate in bounds
    if get_fixed_tier(normalized) is not None:
        return (None, None)

    position = get_stage_position(normalized)
    if position is None:
        return (None, None)

    # Use unified DYNAMIC_STAGE_ORDER for bounds
    lower_bound = None
    earlier_stages = DYNAMIC_STAGE_ORDER[:position]
    if earlier_stages:
        earlier_variants = _get_all_variants_for_stages(earlier_stages)
        if earlier_variants:
            lower_bound = db.session.query(func.max(Releases.fab_order)).filter(
                Releases.stage.in_(earlier_variants),
                Releases.fab_order.isnot(None),
                Releases.is_archived != True,  # noqa: E712
                or_(
                    Releases.job != current_job_id,
                    Releases.release != current_release
                )
            ).scalar()

    upper_bound = None
    later_stages = DYNAMIC_STAGE_ORDER[position + 1:]
    if later_stages:
        later_variants = _get_all_variants_for_stages(later_stages)
        if later_variants:
            upper_bound = db.session.query(func.min(Releases.fab_order)).filter(
                Releases.stage.in_(later_variants),
                Releases.fab_order.isnot(None),
                Releases.is_archived != True,  # noqa: E712
                or_(
                    Releases.job != current_job_id,
                    Releases.release != current_release
                )
            ).scalar()

    return (lower_bound, upper_bound)


def clamp_fab_order(value, lower, upper, strict_upper=False):
    """Clamp a fab_order value to stay within stage bounds.

    strict_upper=True: clamp when value >= upper (stage change path, no collision detection)
    strict_upper=False: clamp only when value > upper (command path, collision handles ties)

    When bounds are inverted (lower >= upper), stage fab_order ranges overlap and
    clamping would collapse any value to 3. Skip bounds clamping in that case.
    """
    # If bounds are inverted, stages overlap — skip lower/upper clamping entirely
    if lower is not None and upper is not None and lower >= upper:
        lower = None
        upper = None
    if lower is not None and value <= lower:
        value = lower + 1
    if upper is not None:
        threshold_hit = (value >= upper) if strict_upper else (value > upper)
        if threshold_hit:
            value = upper - 1
    # Tiers 1-2 are reserved; dynamic fab_order must be >= 3
    if value < 3:
        value = 3
    return value


def get_stage_group_from_stage(stage: Optional[str]) -> Optional[str]:
    """
    Map a stage name to its corresponding stage_group.
    
    Handles both user-provided stage names and actual stage names used in the codebase.
    
    Args:
        stage: Stage name (e.g., 'Released', 'Cut Start', 'Cut start', 'Paint Complete', etc.)
        
    Returns:
        Stage group name (e.g., 'FABRICATION', 'READY_TO_SHIP', 'COMPLETE') or None if stage is not mapped
    """
    if not stage:
        return None
    # Try exact match first
    if stage in STAGE_TO_GROUP:
        return STAGE_TO_GROUP[stage]
    # Try case-insensitive match as fallback
    stage_lower = stage.lower()
    for key, value in STAGE_TO_GROUP.items():
        if key.lower() == stage_lower:
            return value
    return None


def determine_stage_from_db_fields(job: Union[Releases, Any]) -> str:
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
            'is_hard_date': job.get('is_hard_date'),
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
                'is_hard_date': job.get('is_hard_date'),
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

