from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from datetime import datetime
from enum import Enum

db = SQLAlchemy()

class SyncStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class ProcoreToken(db.Model):
    '''Model to store Procore access token metadata for client credentials flow.
    
    Note: refresh_token field exists in the schema but is not used for client credentials flow.
    New tokens are requested directly using client_id/client_secret when they expire.
    '''
    __tablename__ = "procore_tokens"
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)  # Not used for client credentials flow
    expires_at = db.Column(db.DateTime, nullable=False)
    token_type = db.Column(db.String(50), default="Bearer")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_current(cls):
        '''Get current Procore token'''
        return cls.query.order_by(cls.updated_at.desc()).first()

class ProcoreWebhookEvents(db.Model):
    '''
    Model to store Procore webhook events
    for purposes of handling multiple webhooks and debouncing.
    '''
    __tablename__ = "procore_webhook_events"
    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, nullable=False)
    project_id = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(50), nullable=False)  # 'create' or 'update'
    last_seen = db.Column(db.DateTime, nullable=False)
    
    # Composite unique constraint on resource_id, project_id, and event_type
    __table_args__ = (
        db.UniqueConstraint('resource_id', 'project_id', 'event_type', name='_procore_webhook_unique'),
    )
    
class ProcoreSubmittal(db.Model):
    __tablename__ = "procore_submittals"
    id = db.Column(db.Integer, primary_key=True)
    submittal_id = db.Column(db.String(255), unique=True, nullable=False)
    procore_project_id = db.Column(db.String(100))
    project_number = db.Column(db.String(100))
    project_name = db.Column(db.String(255))
    title = db.Column(db.Text)
    status = db.Column(db.String(100))
    type = db.Column(db.String(100))
    ball_in_court = db.Column(db.String(255))  # Increased to handle multiple assignees (comma-separated)
    submittal_manager = db.Column(db.String(255))
    order_number = db.Column(db.Float)
    notes = db.Column(db.Text)
    submittal_drafting_status = db.Column(db.String(50), nullable=False, default='')
    was_multiple_assignees = db.Column(db.Boolean, default=False)  # Track if submittal was previously in multiple-assignee state
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "submittal_id": self.submittal_id,
            "procore_project_id": self.procore_project_id,
            "project_number": self.project_number,
            "project_name": self.project_name,
            "title": self.title,
            "status": self.status,
            "type": self.type,
            "ball_in_court": self.ball_in_court,
            "submittal_manager": self.submittal_manager,
            "order_number": self.order_number,
            "notes": self.notes,
            "submittal_drafting_status": self.submittal_drafting_status,
            "was_multiple_assignees": self.was_multiple_assignees,
            "last_updated": self.last_updated,
            "created_at": self.created_at,
        }

class SyncOperation(db.Model):
    """Track individual sync operations."""
    __tablename__ = "sync_operations"
    
    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    operation_type = db.Column(db.String(50), nullable=False, index=True)  # 'trello_webhook', etc. (onedrive_poll removed)
    status = db.Column(db.Enum(SyncStatus), nullable=False, default=SyncStatus.PENDING)
    
    # Timing
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    
    # Source information
    source_system = db.Column(db.String(20), nullable=True)  # 'trello', 'system' (onedrive removed)
    source_id = db.Column(db.String(100), nullable=True)  # card_id, file_id, etc.
    
    # Operation details
    records_processed = db.Column(db.Integer, default=0)
    records_updated = db.Column(db.Integer, default=0)
    records_created = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    
    # Error information
    error_type = db.Column(db.String(100), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    error_details = db.Column(db.JSON, nullable=True)
    
    # Additional metadata
    context = db.Column(db.JSON, nullable=True)
    
    # def __repr__(self):
    #     return f"<SyncOperation {self.operation_id} - {self.operation_type} - {self.status}>"
    
    def to_dict(self):
        from app.datetime_utils import format_datetime_mountain
        return {
            'id': self.id,
            'operation_id': self.operation_id,
            'operation_type': self.operation_type,
            'status': self.status.value,
            'started_at': format_datetime_mountain(self.started_at),
            'completed_at': format_datetime_mountain(self.completed_at),
            'duration_seconds': self.duration_seconds,
            'source_system': self.source_system,
            'source_id': self.source_id,
            'records_processed': self.records_processed,
            'records_updated': self.records_updated,
            'records_created': self.records_created,
            'records_failed': self.records_failed,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'metadata': self.context
        }

class SyncLog(db.Model):
    """Detailed log of sync operations for audit trail."""
    __tablename__ = "sync_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.String(32), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    level = db.Column(db.String(10), nullable=False)  # DEBUG, INFO, WARNING, ERROR
    message = db.Column(db.Text, nullable=False)
    
    # Context information
    job_id = db.Column(db.Integer, nullable=True, index=True)
    trello_card_id = db.Column(db.String(64), nullable=True, index=True)
    excel_identifier = db.Column(db.String(20), nullable=True, index=True)  # job-release format
    
    # Additional structured data
    data = db.Column(db.JSON, nullable=True)
    
    def __repr__(self):
        return f"<SyncLog {self.operation_id} - {self.level} - {self.message[:50]}...>"


class Job(db.Model):
    __tablename__ = "jobs"
    __table_args__ = (db.UniqueConstraint("job", "release", name="_job_release_uc"),)
    id = db.Column(db.Integer, primary_key=True)
    # Job # and Release # for identifiers
    job = db.Column(db.Integer, nullable=False)
    release = db.Column(db.String(16), nullable=False)

    # Excel columns
    job_name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(256))
    fab_hrs = db.Column(db.Float)
    install_hrs = db.Column(db.Float)
    paint_color = db.Column(db.String(64))
    pm = db.Column(db.String(16))
    by = db.Column(db.String(16))
    released = db.Column(db.Date)
    fab_order = db.Column(db.Float)
    cut_start = db.Column(db.String(8))
    fitup_comp = db.Column(db.String(8))
    welded = db.Column(db.String(8))
    paint_comp = db.Column(db.String(8))
    ship = db.Column(db.String(8))  # Changed from ship_start to ship
    start_install = db.Column(
        db.Date
    )  # Changed from install to start_install and Date type
    start_install_formula = db.Column(db.String(256))  # New field for formula
    start_install_formulaTF = db.Column(db.Boolean)  # New field for formula check
    comp_eta = db.Column(db.Date)  # Changed from String to Date
    job_comp = db.Column(db.String(8))
    invoiced = db.Column(db.String(8))
    notes = db.Column(db.String(256))

    # Trello fields
    trello_card_id = db.Column(db.String(64), unique=True, nullable=True)
    trello_card_name = db.Column(db.String(256), nullable=True)
    trello_list_id = db.Column(db.String(64), nullable=True)
    trello_list_name = db.Column(db.String(128), nullable=True)
    trello_card_description = db.Column(db.String(512), nullable=True)
    trello_card_date = db.Column(db.Date, nullable=True)
    viewer_url = db.Column(db.String(512), nullable=True)

    # Changelog tracking
    last_updated_at = db.Column(db.DateTime, nullable=True)
    source_of_update = db.Column(
        db.String(16), nullable=True
    )  # 'Trello' or 'Excel' or 'System'

    def __repr__(self):
        return f"<Job {self.job} - {self.release} - {self.job_name}>"
    
    def to_dict(self):
        """
        Return raw job data as a dictionary.
        All fields are included with their original types (dates remain as date objects).
        Use helper functions in app.api.helpers for transformations.
        """
        return {
            "id": self.id,
            "job": self.job,
            "release": self.release,
            "job_name": self.job_name,
            "description": self.description,
            "fab_hrs": self.fab_hrs,
            "install_hrs": self.install_hrs,
            "paint_color": self.paint_color,
            "pm": self.pm,
            "by": self.by,
            "released": self.released,
            "fab_order": self.fab_order,
            "cut_start": self.cut_start,
            "fitup_comp": self.fitup_comp,
            "welded": self.welded,
            "paint_comp": self.paint_comp,
            "ship": self.ship,
            "start_install": self.start_install,
            "start_install_formula": self.start_install_formula,
            "start_install_formulaTF": self.start_install_formulaTF,
            "comp_eta": self.comp_eta,
            "job_comp": self.job_comp,
            "invoiced": self.invoiced,
            "notes": self.notes,
            "trello_card_id": self.trello_card_id,
            "trello_card_name": self.trello_card_name,
            "trello_list_id": self.trello_list_id,
            "trello_list_name": self.trello_list_name,
            "trello_card_description": self.trello_card_description,
            "trello_card_date": self.trello_card_date,
            "viewer_url": self.viewer_url,
            "last_updated_at": self.last_updated_at,
            "source_of_update": self.source_of_update,
        }


def query_job_releases():
    results = Job.query.all()
    return pd.DataFrame(
        [
            {
                "Job #": r.job,
                "Release #": r.release,
                "Job": r.job_name,
                "Description": r.description,
                "Fab Hrs": r.fab_hrs,
                "Install HRS": r.install_hrs,
                "Paint color": r.paint_color,
                "PM": r.pm,
                "BY": r.by,
                "Released": r.released,
                "Fab Order": r.fab_order,
                "Cut start": r.cut_start,
                "Fitup comp": r.fitup_comp,
                "Welded": r.welded,
                "Paint Comp": r.paint_comp,
                "Ship": r.ship,  # Updated field name
                "Start install": r.start_install,  # Updated field name
                "Comp. ETA": r.comp_eta,
                "Job Comp": r.job_comp,
                "Invoiced": r.invoiced,
                "Notes": r.notes,
            }
            for r in results
        ]
    )

class JobEvents(db.Model):
    '''Table to track events for jobs.'''
    __tablename__ = 'job_events'
    id = db.Column(db.Integer, primary_key=True)
    job = db.Column(db.Integer, nullable=False)
    release = db.Column(db.String(50))
    action = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    source = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    applied_at = db.Column(db.DateTime, nullable=True)

class SubmittalEvents(db.Model):
    '''Table to track events for submittals.'''
    __tablename__ = 'submittal_events'
    id = db.Column(db.Integer, primary_key=True)
    submittal_id = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    source = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    applied_at = db.Column(db.DateTime, nullable=True)

class SyncCursor(db.Model):
    __tablename__ = "sync_cursor"
    name = db.Column(db.String, primary_key=True)  # e.g., 'jobs'
    last_updated_at = db.Column(db.DateTime, nullable=False)
    last_id = db.Column(db.Integer, nullable=False)

class Outbox(db.Model):
    """Outbox table for tracking external API calls with retry capabilities."""
    __tablename__ = "outbox"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('job_events.id'), nullable=False, unique=True)
    destination = db.Column(db.String(50), nullable=False)  # 'trello' or 'procore'
    action = db.Column(db.String(50), nullable=False)  # 'move_card', 'update_card', etc.
    
    # Retry tracking
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, processing, completed, failed
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=5)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationship
    event = db.relationship('JobEvents', backref='outbox_items')