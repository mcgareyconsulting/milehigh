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
import re
from datetime import datetime, date
from enum import Enum
from sqlalchemy import cast, Integer, String

db = SQLAlchemy()


def _dt(value):
    """Serialize a datetime/date to ISO format string, or None."""
    return value.isoformat() if value else None


def is_gc_approval_type(type_value):
    """True if `type_value` is a "Submittal for GC Approval", tolerant of the
    casing/double-space variants Procore/our data actually contains (e.g.
    "Submittal for GC  Approval", "Submittal for Gc Approval")."""
    normalized = re.sub(r"\s+", " ", (type_value or "").strip()).lower()
    return normalized == "submittal for gc approval"

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
    # Phase-1 access flag for the read-only BB (Banana Boy) chat assistant. Toggled
    # per-user from the admin UI so we can roll the feature out incrementally without
    # a redeploy. server_default keeps the ADD COLUMN metadata-only on Postgres.
    is_bb_chat = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
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
    project_number = db.Column(db.String(100), index=True)
    project_name = db.Column(db.String(255))
    title = db.Column(db.Text)
    status = db.Column(db.String(100), index=True)
    type = db.Column(db.String(100))
    ball_in_court = db.Column(db.String(255), index=True)  # Increased to handle multiple assignees (comma-separated)
    submittal_manager = db.Column(db.String(255))
    order_number = db.Column(db.Float, index=True)
    notes = db.Column(db.Text)
    submittal_drafting_status = db.Column(db.String(50), nullable=False, default='')
    due_date = db.Column(db.Date, nullable=True)  # Due date for submittal
    # Optional GC-provided jobsite install schedule date for a Sub-GC-type submittal.
    # Setting it also backdates due_date 60 business days from it (see
    # DraftingWorkLoadService.GC_SCHEDULE_LEAD_BUSINESS_DAYS). Tracked as its own column
    # (not just folded into due_date) so it can be analyzed on its own long-term; currently
    # only meaningful for Sub-GC submittals but not enforced at the column level.
    gc_jobsite_schedule_date = db.Column(db.Date, nullable=True)
    # Release identifier (101-998) shown in the DWL Rel column. Suggested as the
    # next highest available value (max-in-use + 1) so assignment is semi-
    # chronological; freed/low numbers are recycled only after REL_MAX is occupied
    # and the sequence rolls over. rel_assigned_at records when it was handed out.
    rel = db.Column(db.Integer, nullable=True)
    rel_assigned_at = db.Column(db.DateTime, nullable=True)
    # Desired install date known ahead of drawings, set on the DWL. Only ever set on
    # DRR submittals that already have a Rel assigned. Hard date only (no ASAP/formula);
    # transfers to the matching Releases row at release creation via PendingStartInstall.
    # Setting it also overwrites due_date with the drawings-due date (15 business days
    # before), so the due date doubles as the Design Drawings Due date.
    start_install = db.Column(db.Date, nullable=True)
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
        return {
            "id": self.id,
            "submittal_id": self.submittal_id,
            "procore_project_id": self.procore_project_id,
            "project_number": self.project_number,
            "project_name": self.project_name,
            "title": self.title,
            "status": self.status,
            "type": self.type,
            "is_gc_approval_type": is_gc_approval_type(self.type),
            "ball_in_court": self.ball_in_court,
            "submittal_manager": self.submittal_manager,
            "order_number": self.order_number,
            "notes": self.notes,
            "submittal_drafting_status": self.submittal_drafting_status,
            "rel": self.rel,
            "due_date": _dt(self.due_date),
            "gc_jobsite_schedule_date": _dt(self.gc_jobsite_schedule_date),
            "start_install": _dt(self.start_install),
            "was_multiple_assignees": self.was_multiple_assignees,
            "last_updated": _dt(self.last_updated),
            "created_at": _dt(self.created_at),
        }

class PendingStartInstall(db.Model):
    """Handoff queue: a desired start-install date set on a DRR submittal in the DWL,
    waiting to be claimed by the matching job-log release when it is created.

    The join key is ``rel``: the pasted Release # on the Job Log equals the DRR's Rel
    (see app.procore.procore._globally_taken_rel_numbers). When a release is created via
    the CSV/TSV paste, release_job_data() looks up the unconsumed pending row for that rel
    and stamps the date onto the new Releases row. ``rel`` is unique-safe because
    assign_rel_manual() forbids two pending DRRs from sharing a Rel.
    """
    __tablename__ = "pending_start_installs"
    id = db.Column(db.Integer, primary_key=True)
    rel = db.Column(db.Integer, unique=True, nullable=False, index=True)  # join key (== future Releases.release)
    job_number = db.Column(db.String(100))   # source Submittals.project_number, for reference/validation
    submittal_id = db.Column(db.String(255))  # source DRR submittal_id
    start_install = db.Column(db.Date, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)  # set when a release claims the date
    consumed_job = db.Column(db.Integer, nullable=True)
    consumed_release = db.Column(db.String(16), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "rel": self.rel,
            "job_number": self.job_number,
            "submittal_id": self.submittal_id,
            "start_install": _dt(self.start_install),
            "consumed_at": _dt(self.consumed_at),
            "consumed_job": self.consumed_job,
            "consumed_release": self.consumed_release,
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
    __table_args__ = (
        db.UniqueConstraint("job", "release", name="_job_release_uc"),
        db.Index("idx_releases_last_updated_at_id", "last_updated_at", "id"),  # cursor poll: filter + ORDER BY match
        db.Index("idx_releases_archived_active", "is_archived", "is_active"),  # every list endpoint
        db.Index("idx_releases_stage_group", "stage_group"),
        db.Index("idx_releases_stage", "stage"),
    )
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
    start_install_asap = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    # True when the install date's color flagging is suppressed (renders neutral, not
    # red/green/yellow). Set by neutralize_install_date_cascade once the release reaches the
    # complete zone (Install Complete/Complete, job_comp='X', invoiced='X') so a finished
    # release doesn't show an alarming date. The start_install value itself is retained.
    start_install_no_color = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    installer = db.Column(db.String(64), nullable=True)  # Installer team; matches Trello list name
    # Installer headcount used to size install duration. Parsed/persisted from the Trello
    # card description ("**Number of Guys:** N"); treated as 2 when absent.
    # comp_eta = start_install + ceil(install_hrs / (num_guys * 8)) business days.
    num_guys = db.Column(db.Float, nullable=True)
    comp_eta = db.Column(db.Date)  # Changed from String to Date
    job_comp = db.Column(db.String(8))
    invoiced = db.Column(db.String(8))
    notes = db.Column(db.String(256))

    # Trello fields
    trello_card_id = db.Column(db.String(64), unique=True, nullable=True)
    # The linked mirror card's id (the installer-team copy). Lets inbound webhooks on the
    # mirror resolve back to this release with a direct lookup instead of an attachment walk.
    mirror_trello_card_id = db.Column(db.String(64), nullable=True)
    trello_card_name = db.Column(db.String(256), nullable=True)
    trello_list_id = db.Column(db.String(64), nullable=True)
    trello_list_name = db.Column(db.String(128), nullable=True)
    trello_card_description = db.Column(db.String(512), nullable=True)
    trello_card_date = db.Column(db.Date, nullable=True)
    viewer_url = db.Column(db.String(512), nullable=True)
    procore_submittal_id = db.Column(db.String(64), nullable=True)

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
            "start_install_asap": self.start_install_asap,
            "start_install_no_color": self.start_install_no_color,
            "installer": self.installer,
            "num_guys": self.num_guys,
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
            "procore_submittal_id": self.procore_submittal_id,
            "has_drawing": False,
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


class SubmittalReconcile(db.Model):
    """
    Delayed reconcile queue for Procore submittals — the safety net for burst-dedup
    and Procore read-after-write lag.

    Every submittal webhook schedules one row here (~60s out). The outbox retry worker
    re-runs check_and_update_submittal, catching any field whose change was dropped by
    burst dedup (is_duplicate_webhook) or had not yet propagated when the live webhook
    was processed. Enqueue is coalescing: at most one 'pending' row per submittal_id,
    so a burst of deliveries produces a single reconcile read.
    """
    __tablename__ = 'submittal_reconcile'
    id = db.Column(db.Integer, primary_key=True)
    submittal_id = db.Column(db.String(255), nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=False)
    scheduled_for = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, processing, completed, failed
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)


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
            d['photos'] = [p.to_dict() for p in
                           self.photos.filter_by(is_deleted=False)
                           .order_by(BoardItemPhoto.uploaded_at.desc(),
                                     BoardItemPhoto.id.desc()).all()]
        return d


class BoardItemPhoto(db.Model):
    """A photo/screenshot attached to a board item for extra dev context.

    Mirrors `ReleasePhoto` (a flat list of independent image rows) but is scoped
    to a `BoardItem` instead of a release, has no stage tag, and carries no
    per-photo caption (context lives in the card body/description).
    """
    __tablename__ = 'board_item_photos'

    id = db.Column(db.Integer, primary_key=True)
    board_item_id = db.Column(db.Integer, db.ForeignKey('board_items.id', ondelete='CASCADE'),
                              nullable=False, index=True)
    storage_key = db.Column(db.String(512), nullable=False)
    original_filename = db.Column(db.String(256), nullable=True)
    mime_type = db.Column(db.String(64), nullable=False, default='image/jpeg')
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    item = db.relationship('BoardItem', backref=db.backref('photos', lazy='dynamic',
                                                           cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])

    @staticmethod
    def _display_name(user):
        if not user:
            return None
        first = (user.first_name or '').strip()
        last = (user.last_name or '').strip()
        return (f"{first} {last}".strip()) or user.username

    def to_dict(self):
        return {
            'id': self.id,
            'board_item_id': self.board_item_id,
            'original_filename': self.original_filename,
            'mime_type': self.mime_type,
            'file_size_bytes': self.file_size_bytes,
            'uploaded_by': {
                'id': self.uploaded_by_user_id,
                'name': self._display_name(self.uploaded_by),
            },
            'uploaded_at': _dt(self.uploaded_at),
        }


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
    checklist_item_id = db.Column(db.Integer, db.ForeignKey('checklist_items.id', ondelete='CASCADE'), nullable=True, index=True)
    drawing_version_comment_id = db.Column(db.Integer, db.ForeignKey('drawing_version_comments.id', ondelete='CASCADE'), nullable=True, index=True)
    bb_drawing_review_id = db.Column(db.Integer, db.ForeignKey('bb_drawing_reviews.id', ondelete='CASCADE'), nullable=True, index=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications', lazy='select')
    board_item = db.relationship('BoardItem', lazy='select')
    board_activity = db.relationship('BoardActivity', lazy='select')
    submittal = db.relationship('Submittals', lazy='select')
    checklist_item = db.relationship('ChecklistItem', lazy='select')
    drawing_version_comment = db.relationship('DrawingVersionComment', lazy='select')
    bb_drawing_review = db.relationship('BBDrawingReview', lazy='select')

    def to_dict(self):
        comment = self.drawing_version_comment
        version = comment.drawing_version if comment else None
        release = comment.release if comment else None
        review = self.bb_drawing_review
        return {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'message': self.message,
            'board_item_id': self.board_item_id,
            'board_activity_id': self.board_activity_id,
            'submittal_id': self.submittal_id,
            'checklist_item_id': self.checklist_item_id,
            'drawing_version_comment_id': self.drawing_version_comment_id,
            'bb_drawing_review_id': self.bb_drawing_review_id,
            'is_read': self.is_read,
            'created_at': _dt(self.created_at),
            'board_item_title': self.board_item.title if self.board_item else None,
            'submittal_title': self.submittal.title if self.submittal else None,
            'submittal_project_name': self.submittal.project_name if self.submittal else None,
            'submittal_project_number': self.submittal.project_number if self.submittal else None,
            # A bb_review notification deep-links to the release report; fall back to the
            # comment's release when this is a drawing-comment mention.
            'release_id': (comment.release_id if comment else None)
                          or (review.release_id if review else None),
            'drawing_version_id': (comment.drawing_version_id if comment else None)
                          or (review.drawing_version_id if review else None),
            'drawing_version_number': version.version_number if version else None,
            'release_job_number': release.job if release else None,
            'release_number': release.release if release else None,
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


class ReleaseDrawingVersion(db.Model):
    """Versioned PDF markup history for a release's For-Construction drawing.

    One PDF per release. Each user save (markup) inserts a new row; original
    upload is version_number=1. `source_version_id` self-links to the version
    a markup was derived from.
    """
    __tablename__ = 'release_drawing_versions'
    __table_args__ = (
        db.UniqueConstraint('release_id', 'version_number', name='_release_version_uc'),
    )

    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False)
    storage_key = db.Column(db.String(512), nullable=False)
    original_filename = db.Column(db.String(256), nullable=True)
    mime_type = db.Column(db.String(64), nullable=False, default='application/pdf')
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    source_version_id = db.Column(
        db.Integer,
        db.ForeignKey('release_drawing_versions.id'),
        nullable=True,
    )
    note = db.Column(db.Text, nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    release = db.relationship('Releases', backref=db.backref('drawing_versions', lazy='dynamic'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])
    source_version = db.relationship('ReleaseDrawingVersion', remote_side=[id])

    def to_dict(self):
        uploaded_by_name = None
        if self.uploaded_by:
            first = (self.uploaded_by.first_name or '').strip()
            last = (self.uploaded_by.last_name or '').strip()
            uploaded_by_name = (f"{first} {last}".strip()) or self.uploaded_by.username
        return {
            'id': self.id,
            'release_id': self.release_id,
            'version_number': self.version_number,
            'original_filename': self.original_filename,
            'mime_type': self.mime_type,
            'file_size_bytes': self.file_size_bytes,
            'uploaded_by': {
                'id': self.uploaded_by_user_id,
                'name': uploaded_by_name,
            },
            'uploaded_at': _dt(self.uploaded_at),
            'source_version_id': self.source_version_id,
            'note': self.note,
        }


class DrawingVersionComment(db.Model):
    """A comment on a specific PDF drawing version, mirroring board comments.

    Each comment can `@FirstName`-mention teammates; the comment routes parse the
    body and create `Notification` rows. `release_id` is denormalized so the
    notification bell can click through to the drawing without a second join.
    """
    __tablename__ = 'drawing_version_comments'
    id = db.Column(db.Integer, primary_key=True)
    drawing_version_id = db.Column(
        db.Integer,
        db.ForeignKey('release_drawing_versions.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    author_name = db.Column(db.String(160), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    drawing_version = db.relationship(
        'ReleaseDrawingVersion',
        backref=db.backref('comments', lazy='dynamic', cascade='all, delete-orphan'),
    )
    release = db.relationship('Releases', lazy='select')

    def to_dict(self):
        return {
            'id': self.id,
            'drawing_version_id': self.drawing_version_id,
            'release_id': self.release_id,
            'body': self.body,
            'author_id': self.author_id,
            'author_name': self.author_name,
            'created_at': _dt(self.created_at),
        }


class ReleasePhoto(db.Model):
    """A photo attached to a release (job-site/progress images).

    Unlike `ReleaseDrawingVersion` (versioned PDFs), photos are a flat list:
    each upload is an independent row. Any image type is allowed and each photo
    carries an optional free-text note that can be edited after upload.
    """
    __tablename__ = 'release_photos'

    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False, index=True)
    storage_key = db.Column(db.String(512), nullable=False)
    original_filename = db.Column(db.String(256), nullable=True)
    mime_type = db.Column(db.String(64), nullable=False, default='image/jpeg')
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    note = db.Column(db.Text, nullable=True)
    # Optional stage tag. Set when a photo is uploaded to satisfy a stage gate
    # (e.g. "Welded QC", "Paint Complete") so the stage-change validation can
    # require proof for that specific stage.
    stage = db.Column(db.String(64), nullable=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # Attribution for the most recent note edit. Photos are open to all users, so
    # these track who last changed a photo's note (and when) after upload. Null
    # until the note is edited for the first time.
    last_edited_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    last_edited_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    release = db.relationship('Releases', backref=db.backref('photos', lazy='dynamic'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])
    last_edited_by = db.relationship('User', foreign_keys=[last_edited_by_user_id])

    @staticmethod
    def _display_name(user):
        if not user:
            return None
        first = (user.first_name or '').strip()
        last = (user.last_name or '').strip()
        return (f"{first} {last}".strip()) or user.username

    def to_dict(self):
        return {
            'id': self.id,
            'release_id': self.release_id,
            'original_filename': self.original_filename,
            'mime_type': self.mime_type,
            'file_size_bytes': self.file_size_bytes,
            'note': self.note,
            'stage': self.stage,
            'uploaded_by': {
                'id': self.uploaded_by_user_id,
                'name': self._display_name(self.uploaded_by),
            },
            'uploaded_at': _dt(self.uploaded_at),
            'last_edited_by': {
                'id': self.last_edited_by_user_id,
                'name': self._display_name(self.last_edited_by),
            } if self.last_edited_by_user_id else None,
            'last_edited_at': _dt(self.last_edited_at),
        }


class FcCollectionRun(db.Model):
    """One row per nightly (or manual) FC PDF Pack retry pass.

    Stores summary counts plus the per-release breakdown so the admin page can
    show stakeholders exactly which releases were missing, which got pulled,
    and which are still outstanding. Table is pruned to the most recent 30 runs
    by the worker after each insert.
    """
    __tablename__ = "fc_collection_runs"
    id = db.Column(db.Integer, primary_key=True)
    run_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    trigger = db.Column(db.String(16), nullable=False, default='cron')  # 'cron' | 'manual'
    candidates = db.Column(db.Integer, nullable=False, default=0)
    succeeded = db.Column(db.Integer, nullable=False, default=0)
    still_missing = db.Column(db.Integer, nullable=False, default=0)
    errored = db.Column(db.Integer, nullable=False, default=0)
    duration_ms = db.Column(db.Integer, nullable=True)
    # details = {
    #   "succeeded":     [{"job": 1234, "release": "V2", "viewer_url": "..."}],
    #   "still_missing": [{"job": 1234, "release": "V3", "reason": "..."}],
    #   "errored":       [{"job": 1234, "release": "V4", "error": "..."}]
    # }
    details = db.Column(db.JSON, nullable=False, default=dict)

    def to_summary_dict(self):
        return {
            'id': self.id,
            'run_at': _dt(self.run_at),
            'trigger': self.trigger,
            'candidates': self.candidates,
            'succeeded': self.succeeded,
            'still_missing': self.still_missing,
            'errored': self.errored,
            'duration_ms': self.duration_ms,
        }

    def to_dict(self):
        d = self.to_summary_dict()
        d['details'] = self.details or {}
        return d


class RawSourceRecord(db.Model):
    """Bronze landing table for the Hive Mind data lake.

    Immutable raw records from any external source (email is the first; Teams
    meetings etc. land here later, distinguished by `source`). The source of
    truth stays in the originating systems — this is a normalized text+structure
    copy for audit, embeddings, and fast joins, with `external_pointer` holding
    references to raw media kept in M365.

    Idempotency: upsert by (source, external_id); `content_hash` detects whether
    a re-pulled record actually changed, so re-pulling an overlapping window is
    safe and lands no duplicates. Plain columns + JSON only (SQLite-test-safe).
    """
    __tablename__ = "raw_source_records"
    __table_args__ = (
        db.UniqueConstraint("source", "external_id", name="uq_raw_source_external_id"),
        db.Index("ix_raw_source_records_content_hash", "content_hash"),
        db.Index("ix_raw_source_records_occurred_at", "occurred_at"),
    )
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(64), nullable=False)         # e.g. 'm365_mail'
    record_type = db.Column(db.String(64), nullable=False)    # e.g. 'email'
    source_account = db.Column(db.String(255), nullable=True)  # mailbox, e.g. 'bb@mhmw.com'
    external_id = db.Column(db.String(1024), nullable=False)  # Graph message id
    content_hash = db.Column(db.String(64), nullable=False)   # sha256 idempotency key
    occurred_at = db.Column(db.DateTime, nullable=True)       # source event time (receivedDateTime)
    ingested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    payload = db.Column(db.JSON, nullable=False)              # normalized record
    external_pointer = db.Column(db.JSON, nullable=True)      # refs kept in M365 (webLink, attachments)
    # Processing metadata (not content): set once the material-order extractor has
    # attempted this record, regardless of outcome, so a non-order email is never
    # re-sent to the LLM on every poll. Reset to NULL when content_hash changes
    # (re-pull with a late attachment) so the changed record is scanned once more.
    material_order_scanned_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "record_type": self.record_type,
            "source_account": self.source_account,
            "external_id": self.external_id,
            "content_hash": self.content_hash,
            "occurred_at": _dt(self.occurred_at),
            "ingested_at": _dt(self.ingested_at),
            "payload": self.payload,
            "external_pointer": self.external_pointer,
        }


class LakeIngestState(db.Model):
    """Per-source watermark for incremental lake ingestion.

    Holds the last poll time and the max `occurred_at` landed so far, so polls
    only fetch records newer than the watermark (minus a small overlap).
    Correctness does not depend on this — RawSourceRecord's (source, external_id)
    uniqueness makes overlapping re-pulls idempotent; the watermark just bounds
    how far back each poll re-reads. Keyed by (source, account) so each mailbox
    in the ingested set advances independently.
    """
    __tablename__ = "lake_ingest_state"
    __table_args__ = (
        db.UniqueConstraint("source", "account", name="uq_lake_ingest_source_account"),
    )
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(64), nullable=False)
    account = db.Column(db.String(255), nullable=True)  # mailbox, e.g. 'bb@mhmw.com'
    last_polled_at = db.Column(db.DateTime, nullable=True)
    last_occurred_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_or_create(cls, source, account=None):
        row = cls.query.filter_by(source=source, account=account).first()
        if row is None:
            row = cls(source=source, account=account)
            db.session.add(row)
            db.session.flush()
        return row


class MicrosoftDelegatedToken(db.Model):
    """Stored delegated OAuth token for a single mailbox identity (device-code flow).

    Used when org policy blocks app-only Graph application permissions: the
    mailbox (bb@mhmw.com) signs in once via the device-code flow and consents
    for itself (user consent, not admin consent). The refresh token here lets
    the poller mint access tokens going forward without further interaction.
    One row per account_email. Tokens are db.Text (no length cap) since refresh
    tokens are large.
    """
    __tablename__ = "microsoft_delegated_tokens"
    id = db.Column(db.Integer, primary_key=True)
    account_email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    scopes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_for_account(cls, account_email):
        return cls.query.filter_by(account_email=(account_email or "").lower()).first()


class MaterialOrder(db.Model):
    """A part/material ordered from a supplier, tagged to a job-release.

    Parsed from supplier order emails forwarded to bb@mhmw.com (the first source
    is Drexel Supply decking orders). Mirrors the "Dencol orders" interaction
    path — it does NOT create a Trello card; it surfaces on the release's detail
    modal as outstanding material. Linked to Releases by (job, release) *value*,
    not a FK, matching how the app links job-log to job sites.

    Lifecycle: status 'ordered' on parse → 'received' when marked (manually for
    now; a receiving-email adapter can close it later). Idempotency: upsert by
    (source_record_id, line_index) so re-ingesting the same email is a no-op.
    Plain columns + simple types only (SQLite-test-safe).
    """
    __tablename__ = "material_orders"
    __table_args__ = (
        db.UniqueConstraint("source_record_id", "line_index", name="uq_material_order_source_line"),
        db.Index("ix_material_orders_job_release", "job", "release"),
        db.Index("ix_material_orders_status", "status"),
    )
    id = db.Column(db.Integer, primary_key=True)
    # Job-release link (by value, not FK — release may be null if the PO only names a job)
    job = db.Column(db.Integer, nullable=True)
    release = db.Column(db.String(16), nullable=True)

    supplier = db.Column(db.String(128), nullable=True)          # e.g. 'Drexel Supply'
    supplier_contact = db.Column(db.String(255), nullable=True)  # rep name/email
    po_number = db.Column(db.String(64), nullable=True)          # e.g. '580-659'
    # Supplier's own order/confirmation number (e.g. Dencol Order #2296464). Null
    # for outbound requests; set when a supplier confirm document carries one.
    supplier_order_no = db.Column(db.String(64), nullable=True)
    # Which artifact this row came from: 'placed' (we sent the order / drawing) vs
    # 'confirmed' (supplier acknowledged it). Seeds the future request↔confirm
    # lifecycle; status stays the ordered/received flag.
    event_type = db.Column(db.String(16), nullable=True)

    # Orderer: the MHMW person who placed the order (the innermost forwarded
    # "From:" sender), NOT the forwarder. Parsed best-effort from the email body.
    ordered_by = db.Column(db.String(128), nullable=True)        # e.g. 'Rourke Alvarado'
    ordered_by_email = db.Column(db.String(255), nullable=True)  # e.g. 'ralvarado@mhmw.com'

    # Order line
    description = db.Column(db.String(512), nullable=True)       # full part text
    quantity = db.Column(db.Float, nullable=True)
    unit = db.Column(db.String(32), nullable=True)               # e.g. 'pcs'
    # Best-effort parsed sub-fields (nullable; description is authoritative)
    profile = db.Column(db.String(64), nullable=True)           # e.g. '1.5C'
    gauge = db.Column(db.String(32), nullable=True)             # e.g. '18Ga'
    finish = db.Column(db.String(64), nullable=True)           # e.g. 'Galvanized'
    dimension = db.Column(db.String(64), nullable=True)        # e.g. '48"'
    # Per-line pricing from a supplier confirm table (null for body/drawing orders).
    unit_price = db.Column(db.Float, nullable=True)
    extended_price = db.Column(db.Float, nullable=True)

    status = db.Column(db.String(16), nullable=False, default="ordered", server_default="ordered")
    ordered_at = db.Column(db.Date, nullable=True)
    received_at = db.Column(db.Date, nullable=True)

    # Provenance: which raw lake record + which line of it this came from
    source = db.Column(db.String(64), nullable=True)            # e.g. 'm365_mail'
    source_record_id = db.Column(db.Integer, nullable=True)    # raw_source_records.id (loose link)
    line_index = db.Column(db.Integer, nullable=False, default=0)
    raw_line = db.Column(db.String(512), nullable=True)        # original order line text

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "job": self.job,
            "release": self.release,
            "supplier": self.supplier,
            "supplier_contact": self.supplier_contact,
            "po_number": self.po_number,
            "supplier_order_no": self.supplier_order_no,
            "event_type": self.event_type,
            "ordered_by": self.ordered_by,
            "ordered_by_email": self.ordered_by_email,
            "description": self.description,
            "quantity": self.quantity,
            "unit": self.unit,
            "profile": self.profile,
            "gauge": self.gauge,
            "finish": self.finish,
            "dimension": self.dimension,
            "unit_price": self.unit_price,
            "extended_price": self.extended_price,
            "status": self.status,
            "ordered_at": _dt(self.ordered_at),
            "received_at": _dt(self.received_at),
            "source": self.source,
            "source_record_id": self.source_record_id,
            "line_index": self.line_index,
            "raw_line": self.raw_line,
            "created_at": _dt(self.created_at),
            "updated_at": _dt(self.updated_at),
        }


class Meeting(db.Model):
    """A captured meeting whose transcript is mined for checklist items.

    MVP: ingestion is stubbed — a transcript is pasted/uploaded via the API rather
    than pulled from Recall.ai/Teams. Maps to the future data-lake
    `core_communication(kind='meeting')`; the Recall/Graph adapters land here later.
    """
    __tablename__ = "meetings"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    # internal_draft | internal_shop | gc_pm | other
    meeting_type = db.Column(db.String(40), nullable=False, default='other')
    source = db.Column(db.String(30), nullable=False, default='stub')  # stub | recall | graph
    project_number = db.Column(db.String(100), nullable=True, index=True)
    occurred_at = db.Column(db.DateTime, nullable=True)   # meeting start (bot join time)
    # Meeting end — stamped when the Recall transcript is pulled (bot leaves the call).
    # Bounds the "during meeting runtime" window used to gather the events that feed the
    # meeting summary: events whose created_at falls in [occurred_at, ended_at].
    ended_at = db.Column(db.DateTime, nullable=True)
    transcript = db.Column(db.Text, nullable=True)
    # Pre-meeting context the user drops in when dispatching the bot (agenda / notes; an
    # uploaded .md lands here too). Feeds to-do EXTRACTION as the authored "before" view —
    # grounds vague references and improves matching. A PDF→text path writes here later.
    agenda_text = db.Column(db.Text, nullable=True)
    # The release/submittal event updates that landed DURING the meeting window — the
    # "events context" rendered for the SUMMARY (and recorded here because state drifts).
    context_snapshot = db.Column(db.Text, nullable=True)
    # The generated meeting summary (events-during-runtime + transcript). The second of the
    # two outputs produced from a meeting, alongside the to-do checklist.
    summary = db.Column(db.Text, nullable=True)
    # Job-log / DWL field snapshots of the entities discussed, captured at meeting START
    # (pre_snapshot, stamped when the bot is dispatched / the meeting is created) and at
    # meeting END (post_snapshot, stamped during extraction once the transcript is in).
    # Comparing them surfaces "the room agreed to change X but the Brain still shows the
    # old value" — see app/brain/meetings/snapshot.py. Shape:
    # {"captured_at": iso, "releases": {"480-146": {field: value}}, "submittals": {...}}.
    pre_snapshot = db.Column(db.JSON, nullable=True)
    post_snapshot = db.Column(db.JSON, nullable=True)
    # Recall.ai notetaker bot dispatched for this meeting (source='recall'). bot_status
    # tracks the bot lifecycle, kept fresh by the recall-webhook receiver.
    meeting_url = db.Column(db.String(1000), nullable=True)
    recall_bot_id = db.Column(db.String(64), nullable=True, index=True)
    bot_status = db.Column(db.String(30), nullable=True)  # scheduled|joining|in_call_recording|done|failed|cancelled
    # Source Graph calendar event id when the bot was scheduled off a calendar invite
    # (calendar → Recall). The poller's idempotency key: one event schedules exactly
    # one bot across polls. NULL for immediate-send and pasted meetings.
    calendar_event_id = db.Column(db.String(255), nullable=True, index=True)
    # Token usage + cost of the LLM to-do extraction (model='stub' / $0 means it fell
    # back to the keyword stub). Stamped each time the checklist is (re)generated.
    extract_model = db.Column(db.String(40), nullable=True)
    extract_input_tokens = db.Column(db.Integer, nullable=True)
    extract_output_tokens = db.Column(db.Integer, nullable=True)
    extract_cost_usd = db.Column(db.Float, nullable=True)
    # On-demand checklist extraction runs in a background thread (the web dyno has no
    # APScheduler — that's the IS_RENDER_SCHEDULER process), because the LLM calls take
    # minutes and would blow past gunicorn's worker timeout if held in the request. The
    # UI polls these instead of waiting on the request. idle|extracting|done|failed.
    extract_status = db.Column(db.String(20), nullable=True, default='idle')
    extract_error = db.Column(db.Text, nullable=True)
    extract_started_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    extracted_at = db.Column(db.DateTime, nullable=True)  # when checklist items were generated
    learned_at = db.Column(db.DateTime, nullable=True)    # when the learnings step last ran
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    items = db.relationship(
        'ChecklistItem', backref='meeting', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    learnings = db.relationship(
        'MeetingLearning', backref='meeting', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    drifts = db.relationship(
        'BrainDrift', backref='meeting', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    created_by_user = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self, include_items=False):
        d = {
            'id': self.id,
            'title': self.title,
            'meeting_type': self.meeting_type,
            'source': self.source,
            'project_number': self.project_number,
            'occurred_at': _dt(self.occurred_at),
            'ended_at': _dt(self.ended_at),
            'extracted_at': _dt(self.extracted_at),
            'learned_at': _dt(self.learned_at),
            'created_at': _dt(self.created_at),
            'meeting_url': self.meeting_url,
            'recall_bot_id': self.recall_bot_id,
            'bot_status': self.bot_status,
            'calendar_event_id': self.calendar_event_id,
            'extract_model': self.extract_model,
            'extract_input_tokens': self.extract_input_tokens,
            'extract_output_tokens': self.extract_output_tokens,
            'extract_cost_usd': self.extract_cost_usd,
            'extract_status': self.extract_status,
            'extract_error': self.extract_error,
        }
        if include_items:
            items = self.items.order_by(ChecklistItem.id).all()
            d['items'] = [i.to_dict() for i in items]
            d['item_count'] = len(items)
            d['transcript'] = self.transcript  # detail view only — keep the list lean
            d['agenda_text'] = self.agenda_text
            d['context_snapshot'] = self.context_snapshot
            d['summary'] = self.summary
            d['pre_snapshot'] = self.pre_snapshot
            d['post_snapshot'] = self.post_snapshot
            d['drifts'] = [dr.to_dict() for dr in self.drifts.order_by(BrainDrift.id).all()]
            latest = self.learnings.order_by(MeetingLearning.id.desc()).first()
            d['learning'] = latest.to_dict() if latest else None
        else:
            d['item_count'] = self.items.count()
        return d


class ChecklistItem(db.Model):
    """An agent-proposed to-do surfaced from a meeting transcript.

    Lifecycle: the extractor creates rows as `status='proposed'` with an inferred
    owner + due date. The reviewer (MVP: Bill) curates each via yes/no/edit — accept
    sets the final owner_user_id + due_date and flips status to 'accepted'; the
    notification worker then pings the owner as the due date approaches.
    """
    __tablename__ = "checklist_items"
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(
        db.Integer, db.ForeignKey('meetings.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    title = db.Column(db.Text, nullable=False)
    detail = db.Column(db.Text, nullable=True)
    # action | needs_gc_update | decision | risk | fyi
    item_type = db.Column(db.String(30), nullable=False, default='action')
    gc_facing = db.Column(db.Boolean, nullable=False, default=False)

    # Agent inference — immutable record of what was proposed
    proposed_owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    proposed_due_date = db.Column(db.Date, nullable=True)
    confidence = db.Column(db.Float, nullable=True)

    # Final, human-curated values (set on accept/edit; owner + date editable)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)

    # Optional links to internal records (expands to the lake reference spine later)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True)
    submittal_id = db.Column(db.String(255), db.ForeignKey('submittals.submittal_id'), nullable=True)

    # A field change the meeting agreed to make to the Brain (job log / DWL), captured by
    # the extractor: {"target": "release"|"submittal", "field": str, "new_value": str}.
    # The reconciliation pass (snapshot.py) compares it to the post-meeting Brain state and
    # sets brain_update_pending=True when the change never landed — i.e. "we said we'd
    # update this but the Brain still shows the old value", a recommended action.
    expected_update = db.Column(db.JSON, nullable=True)
    brain_update_pending = db.Column(db.Boolean, nullable=False, default=False,
                                     server_default='0')

    # Owner inference (when no owner was stated): which active job it matched + whether
    # the owner was inferred. `confidence` doubles as the match confidence (0..1).
    owner_inferred = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    matched_job_number = db.Column(db.String(32), nullable=True)
    matched_job_name = db.Column(db.String(128), nullable=True)  # canonical name from the matched job
    match_source = db.Column(db.String(16), nullable=True)        # release | submittal
    name_corrected = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    # proposed | accepted | rejected | done
    status = db.Column(db.String(20), nullable=False, default='proposed', index=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    last_notified_at = db.Column(db.DateTime, nullable=True)  # last deadline ping (audit)
    last_notified_state = db.Column(db.String(10), nullable=True)  # None | 'due' | 'overdue' — dedup key
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # joined eager-load avoids an N+1 on owner-name lookups when serializing item lists
    owner = db.relationship('User', foreign_keys=[owner_user_id], lazy='joined')
    proposed_owner = db.relationship('User', foreign_keys=[proposed_owner_user_id], lazy='joined')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    # The concrete linked release (when matched/picked) — surfaces its job-release # and
    # description to the reviewer. Joined to avoid an N+1 when serializing item lists.
    release = db.relationship('Releases', foreign_keys=[release_id], lazy='joined')

    @staticmethod
    def _name(u):
        if not u:
            return None
        full = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip()
        return full or u.username

    def to_dict(self):
        return {
            'id': self.id,
            'meeting_id': self.meeting_id,
            'title': self.title,
            'detail': self.detail,
            'item_type': self.item_type,
            'gc_facing': self.gc_facing,
            'proposed_owner_user_id': self.proposed_owner_user_id,
            'proposed_owner_name': self._name(self.proposed_owner),
            'proposed_due_date': _dt(self.proposed_due_date),
            'owner_user_id': self.owner_user_id,
            'owner_name': self._name(self.owner),
            'due_date': _dt(self.due_date),
            'release_id': self.release_id,
            'release_job_release': (f"{self.release.job}-{self.release.release}"
                                    if self.release else None),
            'release_description': (self.release.description if self.release else None),
            'submittal_id': self.submittal_id,
            'expected_update': self.expected_update,
            'brain_update_pending': self.brain_update_pending,
            'status': self.status,
            'confidence': self.confidence,           # match confidence when owner_inferred
            'owner_inferred': self.owner_inferred,
            'matched_job_number': self.matched_job_number,
            'matched_job_name': self.matched_job_name,
            'match_source': self.match_source,
            'name_corrected': self.name_corrected,
            'reviewed_at': _dt(self.reviewed_at),
            'created_at': _dt(self.created_at),
        }


class MeetingLearning(db.Model):
    """What the agent learned from a meeting once the human worked its checklist.

    Synthesized on review completion from {agenda, transcript, event snapshot, the
    yes/no/edit review outcomes}. `summary` is the human-readable insight; `payload`
    structures it by the three dimensions the learnings are keyed on:
    by_outcome (accepted/rejected/edited), by_item_type, and by_event (the underlying
    release/submittal activity). Reusable cross-meeting signals distilled here are stored
    separately in ExtractionSignal so future extractions can read them back.
    """
    __tablename__ = "meeting_learnings"
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(
        db.Integer, db.ForeignKey('meetings.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    summary = db.Column(db.Text, nullable=True)
    payload = db.Column(db.JSON, nullable=True)
    # Usage meter, mirroring Meeting.extract_* ('stub'/$0 = LLM synthesis was skipped).
    model = db.Column(db.String(40), nullable=True)
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    cost_usd = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'meeting_id': self.meeting_id,
            'summary': self.summary,
            'payload': self.payload,
            'model': self.model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cost_usd': self.cost_usd,
            'created_at': _dt(self.created_at),
        }


class BrainDrift(db.Model):
    """A place where the meeting's spoken reality diverges from the Brain (job log / DWL).

    Produced by the read-only drift-detection pass (app/brain/meetings/brain_delta.py):
    for every release/submittal the room discussed, it compares what was SAID against the
    current field value in the system of record and records each mismatch — both
    `contradiction` (a status statement that disagrees, e.g. "that's at 25%" vs
    job_comp=20%) and `agreed_change` (a change the room agreed that never landed). This
    SUBSUMES the v2 ChecklistItem.brain_update_pending flag.

    v3 only DETECTS and surfaces drifts (status stays 'open'); it never writes back to the
    Brain. `status` is the forward hook for the medium-term HITL review loop (open →
    accepted/dismissed → applied) and the long-term live-update path — add reviewed_by /
    decided_at / applied_at columns then; v3 leaves them off.
    """
    __tablename__ = "brain_drifts"
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(
        db.Integer, db.ForeignKey('meetings.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    target = db.Column(db.String(12), nullable=False)   # release | submittal
    ref = db.Column(db.String(64), nullable=True)        # display token: '480-625' / submittal id
    entity_name = db.Column(db.String(255), nullable=True)  # job/project name for display
    field = db.Column(db.String(40), nullable=False)     # a RELEASE_FIELDS / SUBMITTAL_FIELDS name
    stated_value = db.Column(db.String(255), nullable=True)   # what the room said
    brain_value = db.Column(db.String(255), nullable=True)    # what the Brain held at detection
    kind = db.Column(db.String(20), nullable=False, default='contradiction')  # contradiction|agreed_change
    quote = db.Column(db.Text, nullable=True)            # verbatim transcript span
    confidence = db.Column(db.Float, nullable=True)
    # Anchors to the system-of-record row (one of the two is set; an unanchored drift is
    # dropped before persistence since it can't be acted on).
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True)
    submittal_id = db.Column(db.String(255), db.ForeignKey('submittals.submittal_id'), nullable=True)
    # open (detected, unreviewed) — the only state v3 sets. HITL adds dismissed/applied later.
    status = db.Column(db.String(20), nullable=False, default='open', server_default='open')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'meeting_id': self.meeting_id,
            'target': self.target,
            'ref': self.ref,
            'entity_name': self.entity_name,
            'field': self.field,
            'stated_value': self.stated_value,
            'brain_value': self.brain_value,
            'kind': self.kind,
            'quote': self.quote,
            'confidence': self.confidence,
            'release_id': self.release_id,
            'submittal_id': self.submittal_id,
            'status': self.status,
            'created_at': _dt(self.created_at),
        }


class ExtractionSignal(db.Model):
    """A reusable, cross-meeting learning fed back into future to-do extractions.

    signal_type:
      - 'alias'     : a garbled meeting name -> the canonical job name (key=garbled,
                      value=canonical). Applied to normalize names BEFORE matching.
      - 'owner_map' : a proposed-owner correction the reviewer made (key=context,
                      value=target user id) so recurring jobs default to the right owner.
      - 'pattern'   : qualitative guidance keyed by item_type / situation (value=text),
                      injected as LEARNED GUIDANCE in the extraction prompt.

    Unique on (signal_type, key): re-observation upserts and bumps `count` rather than
    duplicating, so a signal earns weight as it recurs across meetings.
    """
    __tablename__ = "extraction_signals"
    __table_args__ = (
        db.UniqueConstraint('signal_type', 'key', name='uq_extraction_signal_type_key'),
    )
    id = db.Column(db.Integer, primary_key=True)
    signal_type = db.Column(db.String(20), nullable=False, index=True)  # alias|owner_map|pattern
    key = db.Column(db.String(255), nullable=False)
    value = db.Column(db.Text, nullable=True)
    count = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    active = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    source_meeting_id = db.Column(
        db.Integer, db.ForeignKey('meetings.id', ondelete='SET NULL'), nullable=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'signal_type': self.signal_type,
            'key': self.key,
            'value': self.value,
            'count': self.count,
            'active': self.active,
            'source_meeting_id': self.source_meeting_id,
            'updated_at': _dt(self.updated_at),
        }


class SunbeltRentalSnapshot(db.Model):
    """One imported Sunbelt 'Equipment on Rent' report — a weekly snapshot.

    All rental lines from a single CSV upload (or, later, a bb@mhmw.com email
    pull) hang off one snapshot so we can diff week-over-week. ``snapshot_date``
    is the report's effective date (defaults to import day; overridable).
    Ingestion goes through app.brain.sunbelt.ingest.ingest_snapshot.
    """
    __tablename__ = 'sunbelt_rental_snapshots'
    id = db.Column(db.Integer, primary_key=True)
    snapshot_date = db.Column(db.Date, nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False, default='upload')  # 'upload' | 'email'
    filename = db.Column(db.String(512))
    row_count = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.String(255))  # username of the admin who imported
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    rentals = db.relationship(
        'SunbeltRental', backref='snapshot', lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'snapshot_date': _dt(self.snapshot_date),
            'source': self.source,
            'filename': self.filename,
            'row_count': self.row_count,
            'created_by': self.created_by,
            'created_at': _dt(self.created_at),
        }


class SunbeltRental(db.Model):
    """One equipment-on-rent line from a Sunbelt report, reconciled to our jobs.

    Raw Sunbelt columns are parsed/typed at ingest; the resolved match
    (matched_job_number / matched_project_name / match_method) is computed by
    app.brain.sunbelt.matching. Discrepancy flags (overdue / on-finished-job /
    cost-outlier) are NOT stored — they are computed at read time relative to
    'today' and current release/submittal state.
    """
    __tablename__ = 'sunbelt_rentals'
    __table_args__ = (
        db.Index('ix_sunbelt_rentals_snapshot', 'snapshot_id'),
        db.Index('ix_sunbelt_rentals_contract', 'contract_number'),
    )
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey('sunbelt_rental_snapshots.id', ondelete='CASCADE'),
        nullable=False,
    )

    # Raw Sunbelt fields (parsed)
    contract_number = db.Column(db.String(40))    # per-line key
    sunbelt_job_label = db.Column(db.String(255))  # Sunbelt "Job #" e.g. "1 - OAK HIL"
    po_number = db.Column(db.String(40))           # Sunbelt "PO_Number" = MHMW job number
    job_location = db.Column(db.String(500))
    ordered_by = db.Column(db.String(255))
    equipment_type = db.Column(db.String(255))
    equipment_number = db.Column(db.String(64))
    make = db.Column(db.String(64))
    model = db.Column(db.String(64))
    quantity = db.Column(db.Integer, default=1)
    est_return_date = db.Column(db.Date)
    day_rate = db.Column(db.Numeric(10, 2))
    week_rate = db.Column(db.Numeric(10, 2))
    four_week_rate = db.Column(db.Numeric(10, 2))
    billed_through = db.Column(db.Date)
    date_rented = db.Column(db.Date)

    # Resolved match (set at ingest)
    matched_job_number = db.Column(db.Integer)
    matched_project_name = db.Column(db.String(255))
    match_method = db.Column(db.String(20))  # po_number | address | submittal | unmatched

    def to_dict(self):
        def _money(v):
            return float(v) if v is not None else None
        return {
            'id': self.id,
            'snapshot_id': self.snapshot_id,
            'contract_number': self.contract_number,
            'sunbelt_job_label': self.sunbelt_job_label,
            'po_number': self.po_number,
            'job_location': self.job_location,
            'ordered_by': self.ordered_by,
            'equipment_type': self.equipment_type,
            'equipment_number': self.equipment_number,
            'make': self.make,
            'model': self.model,
            'quantity': self.quantity,
            'est_return_date': _dt(self.est_return_date),
            'day_rate': _money(self.day_rate),
            'week_rate': _money(self.week_rate),
            'four_week_rate': _money(self.four_week_rate),
            'billed_through': _dt(self.billed_through),
            'date_rented': _dt(self.date_rented),
            'matched_job_number': self.matched_job_number,
            'matched_project_name': self.matched_project_name,
            'match_method': self.match_method,
        }


class BBDrawingReview(db.Model):
    """A Banana Boy code-compliance review of one PDF drawing version.

    Kicked off from the PDF-mentions surface (admin-only). The review runs on a
    background thread (app/brain/pdf_review/worker.py) because the Claude call
    takes minutes; the row moves `pending` -> `complete` | `error` and stores the
    strict-JSON findings plus token usage for cost tracking.
    """
    __tablename__ = 'bb_drawing_reviews'

    id = db.Column(db.Integer, primary_key=True)
    # drawing_version_id/release_id are the release-keyed path (a review of a
    # ReleaseDrawingVersion). They are nullable because a submittal-keyed review
    # (pulled straight from Procore, no job-log release) omits them and instead sets
    # submittal_id + attachment_id below.
    drawing_version_id = db.Column(
        db.Integer,
        db.ForeignKey('release_drawing_versions.id', ondelete='CASCADE'),
        nullable=True, index=True,
    )
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True, index=True)
    # Submittal-keyed path: the Procore submittal id and the prostore attachment id of
    # the reviewed drawing. Set together (release/version null) when the review is run
    # directly off a Procore submittal drawing.
    submittal_id = db.Column(db.String(64), nullable=True, index=True)
    attachment_id = db.Column(db.BigInteger, nullable=True, index=True)
    status = db.Column(db.String(16), nullable=False, default='pending')  # pending|complete|error
    findings = db.Column(db.JSON, nullable=True)   # list of finding dicts when complete
    model = db.Column(db.String(64), nullable=True)
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    error = db.Column(db.Text, nullable=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    drawing_version = db.relationship(
        'ReleaseDrawingVersion',
        backref=db.backref('bb_reviews', lazy='dynamic', cascade='all, delete-orphan'),
    )
    requested_by = db.relationship('User', foreign_keys=[requested_by_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'drawing_version_id': self.drawing_version_id,
            'release_id': self.release_id,
            'submittal_id': self.submittal_id,
            'attachment_id': self.attachment_id,
            'status': self.status,
            'findings': self.findings if self.findings is not None else [],
            'model': self.model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'error': self.error,
            'requested_by_user_id': self.requested_by_user_id,
            'created_at': _dt(self.created_at),
            'completed_at': _dt(self.completed_at),
        }


class BBReviewFeedback(db.Model):
    """A PM's accept/deny (+ optional notes) on ONE finding of a Banana Boy review.

    The training loop: as a PM works a BB report they mark each suggestion accepted or
    rejected and can leave a note ("BB is right, this rise is 8\"" / "false alarm, that
    flight pours into a topping slab"). We just land these to the DB with enough context
    (the finding snapshot + review/release/version + rule_id) to ingest later into the
    rule library. One row per (review, finding); re-submitting a finding upserts it.

    `finding_index` is the position of the finding in the ranked report list the PM sees
    (app/brain/pdf_review/report.build_report -> findings[]); it's stable for a given
    review because the report sort is deterministic. `finding_snapshot` freezes the whole
    finding dict so the feedback stays meaningful even if the rule text later changes.
    """
    __tablename__ = 'bb_review_feedback'
    __table_args__ = (
        db.UniqueConstraint('review_id', 'finding_index', name='_bb_review_feedback_finding_uc'),
    )

    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(
        db.Integer,
        db.ForeignKey('bb_drawing_reviews.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    # Release-keyed context (nullable so submittal-keyed feedback can leave them null).
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True, index=True)
    drawing_version_id = db.Column(db.Integer, nullable=True)
    # Submittal-keyed context: mirrors BBDrawingReview's submittal_id/attachment_id so
    # feedback on a submittal-keyed review carries the same anchor for the training loop.
    submittal_id = db.Column(db.String(64), nullable=True, index=True)
    attachment_id = db.Column(db.BigInteger, nullable=True, index=True)
    finding_index = db.Column(db.Integer, nullable=False)
    rule_id = db.Column(db.String(64), nullable=True)
    decision = db.Column(db.String(16), nullable=False)  # accepted | rejected
    notes = db.Column(db.Text, nullable=True)
    finding_snapshot = db.Column(db.JSON, nullable=True)  # the finding dict at feedback time
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    review = db.relationship('BBDrawingReview', lazy='select')
    user = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'review_id': self.review_id,
            'release_id': self.release_id,
            'drawing_version_id': self.drawing_version_id,
            'submittal_id': self.submittal_id,
            'attachment_id': self.attachment_id,
            'finding_index': self.finding_index,
            'rule_id': self.rule_id,
            'decision': self.decision,
            'notes': self.notes,
            'user_id': self.user_id,
            'created_at': _dt(self.created_at),
            'updated_at': _dt(self.updated_at),
        }


class BBChatConversation(db.Model):
    """A single BB (Banana Boy) chat thread owned by one user.

    Phase-1 chat is read-only — no message ever mutates app data. We persist the
    thread so we have a durable audit trail and an in-app spend ledger keyed to
    the Anthropic request-ids on each assistant turn.
    """
    __tablename__ = "bb_chat_conversations"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=True)
    # The release/submittal this thread is centered on. Set when the user names an entity;
    # every turn re-assembles the lifecycle bundle from this anchor so follow-ups see fresh
    # data. Re-anchored when the user names a different entity mid-thread.
    anchor_kind = db.Column(db.String(16), nullable=True)  # 'release' | 'submittal' | None
    anchor_job = db.Column(db.Integer, nullable=True)
    anchor_release = db.Column(db.String(16), nullable=True)
    anchor_submittal_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = db.relationship(
        "BBChatMessage", backref="conversation", lazy="dynamic",
        cascade="all, delete-orphan", order_by="BBChatMessage.id",
    )

    def to_dict(self, with_messages=False):
        d = {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "anchor": {
                "kind": self.anchor_kind,
                "job": self.anchor_job,
                "release": self.anchor_release,
                "submittal_id": self.anchor_submittal_id,
            } if self.anchor_kind else None,
            "created_at": _dt(self.created_at),
            "updated_at": _dt(self.updated_at),
        }
        if with_messages:
            d["messages"] = [m.to_dict() for m in self.messages]
        return d


class BBChatMessage(db.Model):
    """One turn in a BB chat thread.

    Assistant turns carry the spend telemetry (model, per-turn token counts,
    computed USD cost, wall-clock duration) plus the Anthropic ``request_id`` so a
    ledger row can be reconciled against the Anthropic dashboard. User turns leave
    those columns null.
    """
    __tablename__ = "bb_chat_messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("bb_chat_conversations.id"), nullable=False, index=True
    )
    role = db.Column(db.String(16), nullable=False)  # 'user' | 'assistant'
    content = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Spend telemetry — assistant turns only.
    anthropic_request_id = db.Column(db.String(64), nullable=True, index=True)
    model = db.Column(db.String(64), nullable=True)
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    cache_read_tokens = db.Column(db.Integer, nullable=True)
    cache_write_tokens = db.Column(db.Integer, nullable=True)
    cost_usd = db.Column(db.Float, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    # How many read-only SQL queries the agent ran for this turn (visibility only).
    tool_calls = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "created_at": _dt(self.created_at),
            "metrics": {
                "request_id": self.anthropic_request_id,
                "model": self.model,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cache_read_tokens": self.cache_read_tokens,
                "cache_write_tokens": self.cache_write_tokens,
                "cost_usd": self.cost_usd,
                "duration_ms": self.duration_ms,
                "tool_calls": self.tool_calls,
            } if self.role == "assistant" else None,
        }
