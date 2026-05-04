"""
@milehigh-header
schema_version: 1
purpose: Central ORM module — defines every SQLAlchemy model and the shared db instance used across the application.
exports:
  db: The shared SQLAlchemy instance (initialized in app factory via db.init_app)
  Releases: Job log entries (alias: Job as Releases in integration code)
  Submittals: Procore submittals (table renamed from procore_submittals in M2)
  ReleaseEvents: Audit event stream for job releases with payload-hash dedup
  User: Authentication model with role flags (is_admin, is_drafter, is_active)
  ...and 16 more
imports_from: [flask_sqlalchemy, sqlalchemy, pandas, datetime]
imported_by: [app/__init__.py, app/seed.py, app/services/outbox_service.py, app/brain/job_log/routes.py, app/trello/sync.py, app/procore/__init__.py, app/auth/utils.py, app/brain/drafting_work_load/service.py, app/sync/db_operations.py, app/api/helpers.py, ...and 80 more]
invariants:
  - Job (table 'jobs') is the legacy job log; Releases (table 'releases') is the current model. Integration code aliases: from app.models import Job as Releases.
  - Submittals was renamed from ProcoreSubmittal; old scripts alias it: from app.models import Submittals as ProcoreSubmittal.
  - Job vs Jobs naming collision: Job = job log entries (table 'jobs'); Projects (formerly Jobs) = geofence/job site records (table 'projects').
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from datetime import datetime, date
from enum import Enum
from sqlalchemy import cast, Integer, String

db = SQLAlchemy()


def _dt(value):
    """Serialize a datetime/date to ISO format string, or None."""
    return value.isoformat() if value else None

class SyncStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class User(db.Model):
    """User model for authentication and authorization."""
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    password_set = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_drafter = db.Column(db.Boolean, default=False, nullable=False)
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
    due_date = db.Column(db.Date, nullable=True)  # Due date for submittal
    was_multiple_assignees = db.Column(db.Boolean, default=False)  # Track if submittal was previously in multiple-assignee state
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_bic_update = db.Column(db.DateTime, nullable=True)  # Cached timestamp of last ball-in-court update from Procore

    def get_last_bic_from_events(self):
        """
        Get the timestamp of the last 'updated' event from source 'Procore'
        where the payload contains 'ball_in_court'.

        This is the dynamic/audit method. For performance-critical list views,
        use the cached last_bic_update column instead.

        Returns:
            datetime or None: The created_at timestamp of the last ball_in_court update event,
                            or None if no such event exists
        """
        from app.models import SubmittalEvents
        
        # Query for all updated events from Procore for this submittal
        # Order by most recent first, then filter in Python for ball_in_court in payload
        # This approach works with both SQLite and PostgreSQL
        events = SubmittalEvents.query.filter(
            SubmittalEvents.submittal_id == str(self.submittal_id),
            SubmittalEvents.action == 'updated',
            SubmittalEvents.source == 'Procore'
        ).order_by(SubmittalEvents.created_at.desc()).all()
        
        # Filter for events where payload contains 'ball_in_court' key
        for event in events:
            if event.payload and isinstance(event.payload, dict) and 'ball_in_court' in event.payload:
                return event.created_at
        
        return None
    
    def get_time_since_ball_in_court_update(self):
        """
        Calculate the time elapsed since the last ball_in_court update.

        Returns:
            timedelta or None: The time difference from now, or None if no update event exists
        """
        last_update = self.get_last_bic_from_events()
        if last_update:
            return datetime.utcnow() - last_update
        return None

    def to_dict(self):
        # Use cached last_bic_update column (populated by backfill migration M7)
        # Do NOT call get_last_bic_from_events() here—it's expensive and only for audit/backfill
        last_ball_update = self.last_bic_update
        time_since_update = (datetime.utcnow() - last_ball_update) if last_ball_update else None
        
        # Calculate days since last ball in court update (aging report)
        days_since_ball_update = None
        if time_since_update:
            days_since_ball_update = int(time_since_update.total_seconds() / 86400)  # Convert seconds to days

        # Lifespan: days since creation (how old the submittal is)
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
            "due_date": _dt(self.due_date),
            "lifespan": lifespan,
            "was_multiple_assignees": self.was_multiple_assignees,
            "last_updated": _dt(self.last_updated),
            "created_at": _dt(self.created_at),
            "last_ball_in_court_update": _dt(last_ball_update),
            "time_since_ball_in_court_update_seconds": time_since_update.total_seconds() if time_since_update else None,
            "days_since_ball_in_court_update": days_since_ball_update,
        }

class SystemLogs(db.Model):
    """System logs table for tracking critical errors and system events."""
    __tablename__ = "system_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    level = db.Column(db.String(10), nullable=False, index=True)  # ERROR, INFO, WARNING, DEBUG
    category = db.Column(db.String(100), nullable=False)  # e.g., 'sync', 'api', 'database', 'auth'
    operation = db.Column(db.String(255), nullable=False)  # e.g., 'trello_webhook', 'job_sync'
    message = db.Column(db.Text, nullable=False)
    context = db.Column(db.JSON, nullable=True)  # Additional structured data (stack traces, error details, etc.)
    
    def __repr__(self):
        return f"<SystemLogs {self.id} - {self.level} - {self.category}/{self.operation}>"
    
    def to_dict(self):
        from app.datetime_utils import format_datetime_mountain
        return {
            'id': self.id,
            'timestamp': format_datetime_mountain(self.timestamp),
            'level': self.level,
            'category': self.category,
            'operation': self.operation,
            'message': self.message,
            'context': self.context
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
    """Legacy job log model - used by OneDrive → Trello pipeline."""
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
    start_install = db.Column(db.Date)  # Changed from install to start_install and Date type
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
    source_of_update = db.Column(db.String(16), nullable=True)  # 'Trello' or 'Excel' or 'System'

    def __repr__(self):
        return f"<Job {self.job} - {self.release} - {self.job_name}>"


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


class Releases(db.Model):
    __tablename__ = "releases"
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
    stage = db.Column(db.String(128), nullable=True)
    stage_group = db.Column(db.String(64), nullable=True)
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
    is_active = db.Column(db.Boolean, default=True, nullable=True)  # False = soft-deleted
    is_archived = db.Column(db.Boolean, default=False, nullable=False, server_default='0')

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
            "stage": self.stage,
            "stage_group": self.stage_group,
            "start_install": self.start_install,
            "start_install_formula": self.start_install_formula,
            "start_install_formulaTF": self.start_install_formulaTF,
            "comp_eta": self.comp_eta,
            "job_comp": self.job_comp,
            "invoiced": self.invoiced,
            "notes": self.notes,
            "stage": self.stage,
            "trello_card_id": self.trello_card_id,
            "trello_card_name": self.trello_card_name,
            "trello_list_id": self.trello_list_id,
            "trello_list_name": self.trello_list_name,
            "trello_card_description": self.trello_card_description,
            "trello_card_date": self.trello_card_date,
            "viewer_url": self.viewer_url,
            "last_updated_at": self.last_updated_at,
            "source_of_update": self.source_of_update,
            "is_active": self.is_active,
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
                "Ship": r.ship,
                "Start install": r.start_install,
                "Comp. ETA": r.comp_eta,
                "Job Comp": r.job_comp,
                "Invoiced": r.invoiced,
                "Notes": r.notes,
            }
            for r in results
        ]
    )

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
    external_user_id = db.Column(db.String(255), nullable=True)  # e.g. Trello/Procore user id from webhook
    is_system_echo = db.Column(db.Boolean, nullable=False, default=False)  # True = echo of our own API call; hidden in UI by default
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
    source = db.Column(db.String(50), nullable=False)  # Brain | Procore
    internal_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    external_user_id = db.Column(db.String(255), nullable=True)  # e.g. Procore user id from webhook
    is_system_echo = db.Column(db.Boolean, nullable=False, default=False)  # True = echo of our own API call; hidden in UI by default
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    applied_at = db.Column(db.DateTime, nullable=True)

class TrelloOutbox(db.Model):
    """Outbox table for Trello API calls (move card, update card, etc.) with retry capabilities."""
    __tablename__ = "trello_outbox"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('release_events.id'), nullable=False, unique=True)
    destination = db.Column(db.String(50), nullable=False)  # 'trello'
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
    event = db.relationship('ReleaseEvents', backref='trello_outbox_items')


class ProcoreOutbox(db.Model):
    """Outbox table for Procore API calls (e.g. submittal status update) with retry capabilities."""
    __tablename__ = "procore_outbox"
    id = db.Column(db.Integer, primary_key=True)
    submittal_id = db.Column(db.String(255), nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)  # e.g. 'update_status'
    request_payload = db.Column(db.JSON, nullable=True)  # e.g. {"status_id": 203238}
    # Metadata we send to Procore / use to detect our own webhooks (per Procore: filter by source_application_id)
    source_application_id = db.Column(db.String(255), nullable=True, index=True)
    
    # Retry tracking (for async processing; DWL status update is sync so often completed immediately)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, processing, completed, failed
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=5)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

class WebhookReceipt(db.Model):
    """
    Deduplication log for incoming Procore webhook deliveries.
    Procore sends burst duplicates (2-5 deliveries within ~7 seconds) for every update.
    A receipt_hash is written on first delivery; retries hit the unique constraint and
    are rejected before any Procore API call is made.

    receipt_hash = sha256("procore:{resource_id}:{project_id}:{reason}:{bucket}")
    where bucket = int(unix_time // WEBHOOK_DEDUP_WINDOW_SECONDS)

    Rows older than a few hours carry no value and can be pruned.
    """
    __tablename__ = 'webhook_receipts'
    id = db.Column(db.Integer, primary_key=True)
    receipt_hash = db.Column(db.String(64), nullable=False, unique=True)
    provider = db.Column(db.String(32), nullable=False, default='procore')
    resource_id = db.Column(db.String(64), nullable=True)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class BoardItem(db.Model):
    """Feature requests, bugs, and tasks tracked on The Board."""
    __tablename__ = "board_items"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    body = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='open')
    priority = db.Column(db.String(20), nullable=False, default='normal')
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    author_name = db.Column(db.String(160), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    position = db.Column(db.Integer, nullable=True)

    activity = db.relationship('BoardActivity', backref='item', lazy='dynamic',
                               cascade='all, delete-orphan')

    def to_dict(self, include_activity=False, activity_count=None):
        d = {
            'id': self.id,
            'title': self.title,
            'body': self.body,
            'category': self.category,
            'status': self.status,
            'priority': self.priority,
            'author_id': self.author_id,
            'author_name': self.author_name,
            'created_at': _dt(self.created_at),
            'updated_at': _dt(self.updated_at),
            'position': self.position,
            'activity_count': activity_count if activity_count is not None else self.activity.filter_by(type='comment').count(),
        }
        if include_activity:
            d['activity'] = [a.to_dict() for a in
                             self.activity.order_by(BoardActivity.created_at.asc()).all()]
        return d


class BoardActivity(db.Model):
    """Activity stream for board items — comments and status changes."""
    __tablename__ = "board_activity"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('board_items.id', ondelete='CASCADE'), nullable=False)
    type = db.Column(db.String(30), nullable=False)  # 'comment' or 'status_change'
    body = db.Column(db.Text, nullable=True)
    old_value = db.Column(db.String(100), nullable=True)
    new_value = db.Column(db.String(100), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    author_name = db.Column(db.String(160), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'item_id': self.item_id,
            'type': self.type,
            'body': self.body,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'author_id': self.author_id,
            'author_name': self.author_name,
            'created_at': _dt(self.created_at),
        }


class Notification(db.Model):
    """In-app notifications for @mentions and other events."""
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False, default='mention')
    message = db.Column(db.Text, nullable=False)
    board_item_id = db.Column(db.Integer, db.ForeignKey('board_items.id', ondelete='CASCADE'), nullable=True)
    board_activity_id = db.Column(db.Integer, db.ForeignKey('board_activity.id', ondelete='CASCADE'), nullable=True)
    submittal_id = db.Column(db.String(255), db.ForeignKey('submittals.submittal_id', ondelete='CASCADE'), nullable=True, index=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications', lazy='select')
    board_item = db.relationship('BoardItem', lazy='select')
    board_activity = db.relationship('BoardActivity', lazy='select')
    submittal = db.relationship('Submittals', lazy='select')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'message': self.message,
            'board_item_id': self.board_item_id,
            'board_activity_id': self.board_activity_id,
            'submittal_id': self.submittal_id,
            'is_read': self.is_read,
            'created_at': _dt(self.created_at),
            'board_item_title': self.board_item.title if self.board_item else None,
            'submittal_title': self.submittal.title if self.submittal else None,
            'submittal_project_name': self.submittal.project_name if self.submittal else None,
            'submittal_project_number': self.submittal.project_number if self.submittal else None,
        }


class ProjectManager(db.Model):
    """Project managers assigned to jobsites."""
    __tablename__ = 'project_managers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    color = db.Column(db.String(50), nullable=False, default='#888888')


class Projects(db.Model):
    """
    Project/job site geofences. Links to job log and DWL by identifier value (job number),
    not by foreign key: jobs come from Excel/Trello (Releases.job), submittals from
    Procore (Submittals.project_number). Use job_number to query:
      - Releases.query.filter(Releases.job == cast(Projects.job_number, Integer))  # Releases.job is int
      - Submittals.query.filter(Submittals.project_number == project.job_number)
    Relationships below provide the same via project.jobs and project.submittals.
    """
    __tablename__ = 'projects'
    __table_args__ = (db.UniqueConstraint('job_number', name='_projects_job_number_uc'),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    job_number = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Map feature columns
    address = db.Column(db.String(500))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    radius_meters = db.Column(db.Float)
    pm_id = db.Column(db.Integer, db.ForeignKey('project_managers.id'))
    # GeoJSON polygon: {"type": "Polygon", "coordinates": [[[lng, lat, z?], ...]]}
    # Single canonical column for both map rendering and on-site filtering.
    geofence_geojson = db.Column(db.JSON)

    pm = db.relationship('ProjectManager', backref='jobsites')

    # Relationship by value: job log rows where Releases.job equals this job_number (job_number is string, Releases.job is int)
    jobs = db.relationship(
        'Releases',
        primaryjoin='cast(Projects.job_number, Integer) == Releases.job',
        foreign_keys='Releases.job',
        lazy='dynamic',
        viewonly=True,
    )
    # Relationship by value: DWL submittals where project_number == this job_number (both strings)
    submittals = db.relationship(
        'Submittals',
        primaryjoin='Submittals.project_number == Projects.job_number',
        foreign_keys='Submittals.project_number',
        lazy='dynamic',
        viewonly=True,
    )
