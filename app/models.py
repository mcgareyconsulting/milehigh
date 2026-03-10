from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from datetime import datetime, date
from enum import Enum
from sqlalchemy import cast, Integer

db = SQLAlchemy()


class User(db.Model):
    """User model for authentication and authorization."""
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    procore_id = db.Column(db.String(255), unique=True, nullable=True)
    trello_id = db.Column(db.String(255), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    job_events = db.relationship(
        'ReleaseEvents', backref='user', lazy='dynamic',
        foreign_keys='ReleaseEvents.internal_user_id'
    )
    submittal_events = db.relationship(
        'SubmittalEvents', backref='user', lazy='dynamic',
        foreign_keys='SubmittalEvents.internal_user_id'
    )

    def __repr__(self):
        return f"<User {self.username}>"

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
    
class Submittals(db.Model):
    __tablename__ = "submittals"
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
    due_date = db.Column(db.Date, nullable=True)
    was_multiple_assignees = db.Column(db.Boolean, default=False)  # Track if submittal was previously in multiple-assignee state
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_last_ball_in_court_update_time(self):
        """
        Get the timestamp of the last 'updated' event from source 'Procore'
        where the payload contains 'ball_in_court'.
        """
        from app.models import SubmittalEvents

        events = SubmittalEvents.query.filter(
            SubmittalEvents.submittal_id == str(self.submittal_id),
            SubmittalEvents.action == 'updated',
            SubmittalEvents.source == 'Procore'
        ).order_by(SubmittalEvents.created_at.desc()).all()

        for event in events:
            if event.payload and isinstance(event.payload, dict) and 'ball_in_court' in event.payload:
                return event.created_at

        return None

    def get_time_since_ball_in_court_update(self):
        last_update = self.get_last_ball_in_court_update_time()
        if last_update:
            return datetime.utcnow() - last_update
        return None

    def to_dict(self):
        last_ball_update = self.get_last_ball_in_court_update_time()
        time_since_update = self.get_time_since_ball_in_court_update()

        days_since_ball_update = None
        if time_since_update:
            days_since_ball_update = int(time_since_update.total_seconds() / 86400)

        lifespan = None
        if self.created_at:
            today = date.today()
            created_date = self.created_at.date() if hasattr(self.created_at, 'date') else self.created_at
            lifespan = (today - created_date).days

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
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "lifespan": lifespan,
            "was_multiple_assignees": self.was_multiple_assignees,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_ball_in_court_update": last_ball_update.isoformat() if last_ball_update else None,
            "time_since_ball_in_court_update_seconds": time_since_update.total_seconds() if time_since_update else None,
            "days_since_ball_in_court_update": days_since_ball_update,
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


class Releases(db.Model):
    __tablename__ = "releases"
    __table_args__ = (db.UniqueConstraint("job", "release", name="_job_release_uc_releases"),)
    id = db.Column(db.Integer, primary_key=True)
    job = db.Column(db.Integer, nullable=False)
    release = db.Column(db.String(16), nullable=False)
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
    ship = db.Column(db.String(8))
    start_install = db.Column(db.Date)
    start_install_formula = db.Column(db.String(256))
    start_install_formulaTF = db.Column(db.Boolean)
    comp_eta = db.Column(db.Date)
    job_comp = db.Column(db.String(8))
    invoiced = db.Column(db.String(8))
    notes = db.Column(db.String(256))
    trello_card_id = db.Column(db.String(64), unique=True, nullable=True)
    trello_card_name = db.Column(db.String(256), nullable=True)
    trello_list_id = db.Column(db.String(64), nullable=True)
    trello_list_name = db.Column(db.String(128), nullable=True)
    trello_card_description = db.Column(db.String(512), nullable=True)
    trello_card_date = db.Column(db.Date, nullable=True)
    viewer_url = db.Column(db.String(512), nullable=True)
    last_updated_at = db.Column(db.DateTime, nullable=True)
    source_of_update = db.Column(db.String(16), nullable=True)
    # Sandbox-only (populated later via Trello webhook shadow mode)
    stage = db.Column(db.String(128), nullable=True)
    stage_group = db.Column(db.String(64), nullable=True)
    banana_color = db.Column(db.String(16), nullable=True)


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


class ReleaseEvents(db.Model):
    '''Table to track events for releases.'''
    __tablename__ = 'release_events'
    __table_args__ = (db.UniqueConstraint('payload_hash', name='uq_release_events_payload_hash'),)
    id = db.Column(db.Integer, primary_key=True)
    job = db.Column(db.Integer, nullable=False)
    release = db.Column(db.String(50))
    action = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    source = db.Column(db.String(50), nullable=False)
    internal_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    external_user_id = db.Column(db.String(255), nullable=True)
    is_system_echo = db.Column(db.Boolean, nullable=False, default=False)
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
    internal_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    external_user_id = db.Column(db.String(255), nullable=True)
    is_system_echo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    applied_at = db.Column(db.DateTime, nullable=True)


class TrelloOutbox(db.Model):
    """Outbox table for Trello API calls with retry capabilities."""
    __tablename__ = "trello_outbox"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('release_events.id'), nullable=False, unique=True)
    destination = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=5)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    event = db.relationship('ReleaseEvents', backref='trello_outbox_items')


class ProcoreOutbox(db.Model):
    """Outbox table for Procore API calls with retry capabilities."""
    __tablename__ = "procore_outbox"
    id = db.Column(db.Integer, primary_key=True)
    submittal_id = db.Column(db.String(255), nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    request_payload = db.Column(db.JSON, nullable=True)
    source_application_id = db.Column(db.String(255), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=5)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)


class WebhookReceipt(db.Model):
    """
    Deduplication log for incoming Procore webhook deliveries.
    receipt_hash = sha256("procore:{resource_id}:{project_id}:{reason}:{bucket}")
    """
    __tablename__ = 'webhook_receipts'
    id = db.Column(db.Integer, primary_key=True)
    receipt_hash = db.Column(db.String(64), nullable=False, unique=True)
    provider = db.Column(db.String(32), nullable=False, default='procore')
    resource_id = db.Column(db.String(64), nullable=True)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class Jobs(db.Model):
    """
    Job site geofences for location-based lookups.
    Note: uses 'job_sites' table name to avoid conflict with main's 'jobs' table (job log).
    """
    __tablename__ = 'job_sites'
    __table_args__ = (db.UniqueConstraint('job_number', name='_job_sites_job_number_uc'),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    job_number = db.Column(db.String(100), nullable=False)
    geometry = db.Column(db.JSON, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    address = db.Column(db.String(500))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    radius_meters = db.Column(db.Float)
    geofence_geojson = db.Column(db.JSON)
