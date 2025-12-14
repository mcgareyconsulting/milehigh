"""
Helper functions for transforming job data for API responses.
"""
from typing import Dict, Any, Union
from app.models import Job
from app.sync.services.trello_list_mapper import TrelloListMapper


def determine_stage_from_db_fields(job: Union[Job, Any]) -> str:
    """
    Determine the stage from database fields using TrelloListMapper logic.
    Returns the stage name or 'Released' if all fields are null/blank.
    
    Args:
        job: Job model instance or object with cut_start, fitup_comp, welded, paint_comp, ship attributes
    """
    # Use TrelloListMapper to determine stage from the 5 columns
    trello_list = TrelloListMapper.determine_trello_list_from_db(job)
    
    # If TrelloListMapper returns a list name, use it as the stage
    if trello_list:
        return trello_list
    
    # If all fields are null/blank, default to 'Released'
    if (not job.cut_start or job.cut_start == '') and \
       (not job.fitup_comp or job.fitup_comp == '') and \
       (not job.welded or job.welded == '') and \
       (not job.paint_comp or job.paint_comp == '') and \
       (not job.ship or job.ship == ''):
        return 'Released'
    
    # If we can't determine a stage but have some values, default to 'Released'
    return 'Released'


def determine_stage_from_job_dict(job_dict: Dict[str, Any]) -> str:
    """
    Determine stage from a job dictionary (used when we have dict instead of Job object).
    This is a helper for transform_job_for_display.
    """
    # Create a simple object-like structure for TrelloListMapper
    class JobLike:
        def __init__(self, d):
            self.cut_start = d.get('cut_start')
            self.fitup_comp = d.get('fitup_comp')
            self.welded = d.get('welded')
            self.paint_comp = d.get('paint_comp')
            self.ship = d.get('ship')
    
    job_like = JobLike(job_dict)
    return determine_stage_from_db_fields(job_like)


def transform_job_for_display(job_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform raw job data (from to_dict()) into display format.
    
    This includes:
    - Determining Stage from the 5 status columns
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
    
    # Determine Stage from the 5 status columns
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

