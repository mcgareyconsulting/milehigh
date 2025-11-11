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
    '''Model to store Procore access token metadata'''
    __tablename__ = "procore_tokens"
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    token_type = db.Column(db.String(50), default="Bearer")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_current(cls):
        '''Get current Procore token'''
        return cls.query.order_by(cls.updated_at.desc()).first()

class SyncOperation(db.Model):
    """Track individual sync operations."""
    __tablename__ = "sync_operations"
    
    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    operation_type = db.Column(db.String(50), nullable=False, index=True)  # 'trello_webhook', 'onedrive_poll', etc.
    status = db.Column(db.Enum(SyncStatus), nullable=False, default=SyncStatus.PENDING)
    
    # Timing
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    
    # Source information
    source_system = db.Column(db.String(20), nullable=True)  # 'trello', 'onedrive', 'system'
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
    
    def __repr__(self):
        return f"<SyncOperation {self.operation_id} - {self.operation_type} - {self.status}>"
    
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

class JobChangeLog(db.Model):
    """Tracks state changes and field updates for jobs over time."""
    __tablename__ = 'job_change_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    job = db.Column(db.Integer, nullable=False)
    release = db.Column(db.String(50))
    
    # Change information
    change_type = db.Column(db.String(50), nullable=False)  # "state_change", "field_change" (future)
    from_value = db.Column(db.String(200))  # Previous state/value (None for initial)
    to_value = db.Column(db.String(200), nullable=False)  # New state/value
    
    # Context
    field_name = db.Column(db.String(100))  # e.g., "fitup_comp", "state" for state changes
    
    # Timing
    changed_at = db.Column(db.DateTime, nullable=False)
    
    # Traceability
    operation_id = db.Column(db.String(36), nullable=True)  # Links to SyncOperation
    source = db.Column(db.String(50), nullable=False)  # "Excel", "Trello", "Manual"
    
    # Optional metadata
    triggered_by = db.Column(db.String(100))  # What caused this change
    
    # Indexes for efficient queries
    __table_args__ = (
        db.Index('idx_job_release', 'job', 'release'),
        db.Index('idx_changed_at', 'changed_at'),
        db.Index('idx_operation_id', 'operation_id'),
        db.Index('idx_change_type', 'change_type'),
    )
    
    def __repr__(self):
        return f"<JobChangeLog {self.job}-{self.release}: {self.from_value}→{self.to_value}>"
