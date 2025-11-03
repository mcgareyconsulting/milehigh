from app.models import db, Job
# COMMENTED OUT: JobChangeLog table not yet migrated in production DB
# from app.models import JobChangeLog
from datetime import datetime, timezone
from app.logging_config import get_logger

logger = get_logger(__name__)


class JobStateConfig:
    """Defines uniform state mapping from DB fields."""
    
    # State definitions based on milestone fields
    STATES = {
        'fitup_comp': 'Fitup Complete',
        'paint_comp': 'Paint Complete',
        'ship': 'Shipped'
    }
    
    # Order of state progression (for determining current state)
    STATE_ORDER = [
        'Created',
        'Fitup Complete',
        'Paint Complete',
        'Shipped'
    ]
    
    @classmethod
    def get_current_state(cls, job_record):
        """Determine current state based on DB field values."""
        # Check fields in reverse order (highest state wins)
        # Only "X" means the milestone is complete, not just any truthy value
        if job_record.ship == "X":
            return 'Shipped'
        if job_record.paint_comp == "X":
            return 'Paint Complete'
        if job_record.fitup_comp == "X":
            return 'Fitup Complete'
        return 'Created'


def track_job_state_change(
    job_record,
    operation_id,
    source,
    previous_state=None,
    triggered_by=None
):
    """
    Track state changes for a job.
    
    Args:
        job_record: Job model instance
        operation_id: SyncOperation ID that caused this change
        source: "Excel" or "Trello"
        previous_state: Previous state (if known), otherwise will query
        triggered_by: Description of what triggered the change
    """
    current_state = JobStateConfig.get_current_state(job_record)
    
    # COMMENTED OUT: JobChangeLog table not yet migrated in production DB
    # # Get previous state if not provided
    # if previous_state is None:
    #     last_change = JobChangeLog.query.filter_by(
    #         job=job_record.job,
    #         release=job_record.release,
    #         change_type='state_change'
    #     ).order_by(JobChangeLog.changed_at.desc()).first()
    #     
    #     previous_state = last_change.to_value if last_change else None
    
    # # Only log if state actually changed
    # if previous_state != current_state:
    #     change_log = JobChangeLog(
    #         job=job_record.job,
    #         release=job_record.release,
    #         change_type='state_change',
    #         from_value=previous_state,
    #         to_value=current_state,
    #         field_name='state',
    #         changed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    #         operation_id=operation_id,
    #         source=source,
    #         triggered_by=triggered_by
    #     )
    #     
    #     db.session.add(change_log)
    #     db.session.commit()
    #     
    #     logger.info(
    #         f"State change tracked: {job_record.job}-{job_record.release}",
    #         from_state=previous_state or "None",
    #         to_state=current_state,
    #         operation_id=operation_id,
    #         source=source
    #     )
    #     
    #     return change_log
    
    # COMMENTED OUT: Return None to prevent errors
    return None


def detect_and_track_state_changes(
    job_record,
    old_values,
    operation_id,
    source
):
    """
    Detect which fields changed and track state transitions.
    
    Args:
        job_record: Current Job record (after update)
        old_values: Dict of previous field values {"fitup_comp": ..., "paint_comp": ..., "ship": ...}
        operation_id: SyncOperation ID
        source: "Excel" or "Trello"
    """
    # Determine previous and current states
    milestone_fields = ['fitup_comp', 'paint_comp', 'ship']
    
    # Create a temporary "old" record to get previous state
    class OldRecord:
        def __init__(self, values):
            for field in milestone_fields:
                setattr(self, field, values.get(field))
    
    old_record = OldRecord(old_values)
    previous_state = JobStateConfig.get_current_state(old_record)
    
    # Check which milestone field(s) changed
    changed_fields = []
    for field in milestone_fields:
        old_val = old_values.get(field)
        new_val = getattr(job_record, field)
        
        if old_val != new_val and new_val is not None:
            changed_fields.append(field)
    
    triggered_by = f"{', '.join(changed_fields)}_changed" if changed_fields else None
    
    # Track the state change
    return track_job_state_change(
        job_record=job_record,
        operation_id=operation_id,
        source=source,
        previous_state=previous_state,
        triggered_by=triggered_by
    )