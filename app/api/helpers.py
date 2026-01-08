"""
Helper functions for transforming job data for API responses.
"""
from typing import Dict, Any, Union
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

