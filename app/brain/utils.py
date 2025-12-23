"""
Utility functions for the Brain

Contains helper functions for processing and transforming Job log data.
"""
from datetime import date, datetime

def determine_stage_from_db_fields(job):
    """
    Determine the job stage from database fields using TrelloListMapper logic.
    
    This function computes a single stage name from the five status columns:
    - cut_start
    - fitup_comp
    - welded
    - paint_comp
    - ship
    
    The stage is determined by:
    1. Using TrelloListMapper.determine_trello_list_from_db() to map the status
       columns to a Trello list name (which represents the stage)
    2. If no stage can be determined but all fields are null/blank, returns 'Released'
    3. Otherwise defaults to 'Released'
    
    Args:
        job: Job model instance with cut_start, fitup_comp, welded, paint_comp,
             and ship attributes
            
    Returns:
        str: The stage name (e.g., 'Cut Start', 'Fit Up Complete', 'Welded',
             'Paint Complete', 'Ship', or 'Released')
             
    Example:
        >>> job = Job.query.first()
        >>> stage = determine_stage_from_db_fields(job)
        >>> print(stage)
        'Cut Start'
    """
    from app.sync.services.trello_list_mapper import TrelloListMapper
    
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

def serialize_value(value):
    """
    Safely serialize a value to a JSON-compatible type.
    
    Handles dates, datetimes, and other non-serializable types.
    """
    if value is None:
        return None
    elif isinstance(value, (date, datetime)):
        return value.isoformat()
    elif isinstance(value, (int, float, str, bool)):
        return value
    elif isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    else:
        # Fallback: convert to string
        return str(value)
