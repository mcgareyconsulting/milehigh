"""
@milehigh-header
schema_version: 1
purpose: Legacy hyphen-path copy of job_log/utils.py -- provides stage resolution and value serialization helpers for the brain module.
exports:
  determine_stage_from_db_fields: Return the stage name from a Job record, defaulting to 'Released'
  serialize_value: Convert Python values (dates, NaN, bytes) to JSON-safe types
imports_from: [datetime, math]
imported_by: []
invariants:
  - This file duplicates app/brain/job_log/utils.py; the underscore-path version is canonical
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Utility functions for the Brain

Contains helper functions for processing and transforming Job log data.
"""
from datetime import date, datetime
import math

def determine_stage_from_db_fields(job):
    """
    Get the stage from the job's stage field.
    
    This function returns the stage name directly from the database stage field,
    or 'Released' if the stage field is None/empty.
    
    Args:
        job: Job model instance with stage attribute
            
    Returns:
        str: The stage name (e.g., 'Cut start', 'Fit Up Complete.', 'Paint complete', etc.)
             or 'Released' if stage is None/empty
             
    Example:
        >>> job = Job.query.first()
        >>> stage = determine_stage_from_db_fields(job)
        >>> print(stage)
        'Cut start'
    """
    # Use stage field directly from database
    if hasattr(job, 'stage') and job.stage:
        return job.stage
    return 'Released'

def serialize_value(value):
    """
    Safely serialize a value to a JSON-compatible type.
    
    Handles dates, datetimes, NaN values, and other non-serializable types.
    """
    if value is None:
        return None
    elif isinstance(value, (date, datetime)):
        return value.isoformat()
    elif isinstance(value, float):
        # Check for NaN and infinity values which aren't valid JSON
        if math.isnan(value):
            return None
        elif math.isinf(value):
            return None
        return value
    elif isinstance(value, (int, str, bool)):
        return value
    elif isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    else:
        # Fallback: convert to string
        return str(value)



