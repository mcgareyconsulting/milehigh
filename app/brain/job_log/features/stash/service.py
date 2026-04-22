"""
@milehigh-header
schema_version: 1
purpose: Manage the Thursday review-meeting stash lifecycle — start/stop/stash/apply/discard of queued job-log edits.
exports:
  StashSessionService: Static methods for session lifecycle and per-change operations
  SessionAlreadyActiveError, SessionNotActiveError, SessionNotFoundError: domain errors
imports_from: [app.models, app.brain.job_log.features.stash.apply, app.brain.job_log.scheduling.service]
imported_by: [app/brain/job_log/routes.py, tests/brain/test_stash_session.py]
invariants:
  - At most one session with status='active' exists globally (enforced by partial unique index)
  - stash_change is upsert on (session_id, job, release, field); baseline_value set only on first insert
  - apply() holds SELECT FOR UPDATE on the session row; applied_at is the idempotency marker
  - Scheduling cascade runs exactly once per apply() invocation, at the end
"""
from datetime import datetime, date
from typing import Optional, Any

from sqlalchemy.exc import IntegrityError

from app.models import (
    StashSession, StashedJobChange, Releases, User, db,
)
from app.brain.job_log.features.stash.apply import apply_change
from app.logging_config import get_logger

logger = get_logger(__name__)


class SessionAlreadyActiveError(Exception):
    """Raised when attempting to start a session while one is already active."""


class SessionNotActiveError(Exception):
    """Raised when attempting to modify/apply/discard a session not in 'active' state."""


class SessionNotFoundError(Exception):
    """Raised when the requested session id doesn't exist."""


# Field apply order: start_install first (affects baseline for later cascades),
# then stage (may cascade fab_order and job_comp), then fab_order, notes,
# job_comp (may cascade stage), invoiced.
_FIELD_APPLY_ORDER = ['start_install', 'stage', 'fab_order', 'notes', 'job_comp', 'invoiced']
_FIELD_ORDER_MAP = {f: i for i, f in enumerate(_FIELD_APPLY_ORDER)}


def _serialize_field_current(record: Releases, field: str) -> Any:
    """Read the current DB value for a given field in the shape stashed changes use."""
    if field == 'stage':
        return record.stage
    if field == 'fab_order':
        return record.fab_order
    if field == 'notes':
        return record.notes
    if field == 'job_comp':
        return record.job_comp
    if field == 'invoiced':
        return record.invoiced
    if field == 'start_install':
        return {
            'date': record.start_install.isoformat() if record.start_install else None,
            'is_hard_date': not bool(record.start_install_formulaTF),
        }
    raise ValueError(f"Unknown field: {field}")


def _values_equal(field: str, a: Any, b: Any) -> bool:
    """Compare two values for a field, handling the start_install dict shape."""
    if field == 'start_install':
        if not isinstance(a, dict) or not isinstance(b, dict):
            return a == b
        a_date = a.get('date')
        b_date = b.get('date')
        return a_date == b_date and bool(a.get('is_hard_date')) == bool(b.get('is_hard_date'))
    # For short fields, treat empty string / None as equal
    if field in ('notes', 'job_comp', 'invoiced'):
        a_n = (a or '').strip() if isinstance(a, str) else a
        b_n = (b or '').strip() if isinstance(b, str) else b
        return (a_n or None) == (b_n or None)
    return a == b


def _serialize_new_value_for_compare(field: str, new_value: Any) -> Any:
    """
    When comparing the queued new_value against the current DB value, derive
    the DB-equivalent shape for start_install:
       {"action": "set", "date": "YYYY-MM-DD", "is_hard_date": true}
         -> {"date": "YYYY-MM-DD", "is_hard_date": true}
       {"action": "clear"} -> {"date": None, "is_hard_date": False}
    """
    if field == 'start_install' and isinstance(new_value, dict):
        if new_value.get('action') == 'clear':
            return {'date': None, 'is_hard_date': False}
        return {
            'date': new_value.get('date'),
            'is_hard_date': bool(new_value.get('is_hard_date', True)),
        }
    return new_value


class StashSessionService:
    @staticmethod
    def get_active() -> Optional[StashSession]:
        return StashSession.query.filter_by(status='active').first()

    @staticmethod
    def get(session_id: int) -> StashSession:
        session = StashSession.query.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"StashSession {session_id} not found")
        return session

    @staticmethod
    def start(user: User) -> StashSession:
        existing = StashSessionService.get_active()
        if existing is not None:
            raise SessionAlreadyActiveError(
                f"A stash session is already active (id={existing.id})"
            )

        session = StashSession(
            started_by_id=user.id,
            status='active',
            started_at=datetime.utcnow(),
        )
        db.session.add(session)
        try:
            db.session.commit()
        except IntegrityError:
            # Partial unique index caught a race with another admin
            db.session.rollback()
            raise SessionAlreadyActiveError("A stash session is already active")

        logger.info(f"Stash session {session.id} started by user {user.id}")
        return session

    @staticmethod
    def stash_change(
        session_id: int,
        job: int,
        release: str,
        field: str,
        new_value: Any,
    ) -> StashedJobChange:
        if field not in _FIELD_ORDER_MAP:
            raise ValueError(f"Unknown field: {field}")

        session = StashSessionService.get(session_id)
        if session.status != 'active':
            raise SessionNotActiveError(f"Session {session_id} is not active")

        change = StashedJobChange.query.filter_by(
            session_id=session_id, job=job, release=release, field=field,
        ).first()

        if change is None:
            record = Releases.query.filter_by(job=job, release=release).first()
            if record is None:
                raise ValueError(f"Release {job}-{release} not found")
            baseline = _serialize_field_current(record, field)
            change = StashedJobChange(
                session_id=session_id,
                job=job,
                release=release,
                field=field,
                baseline_value=baseline,
                new_value=new_value,
                status='pending',
            )
            db.session.add(change)
        else:
            change.new_value = new_value
            change.updated_at = datetime.utcnow()
            # If a prior apply attempt marked this as failed/conflict, reset to pending
            change.status = 'pending'
            change.error = None
            change.applied_at = None

        db.session.commit()
        return change

    @staticmethod
    def remove_change(session_id: int, change_id: int) -> None:
        session = StashSessionService.get(session_id)
        if session.status != 'active':
            raise SessionNotActiveError(f"Session {session_id} is not active")

        change = StashedJobChange.query.filter_by(
            id=change_id, session_id=session_id,
        ).first()
        if change is None:
            raise ValueError(f"Change {change_id} not found in session {session_id}")

        db.session.delete(change)
        db.session.commit()

    @staticmethod
    def preview(session_id: int) -> dict:
        session = StashSessionService.get(session_id)
        changes = StashedJobChange.query.filter_by(session_id=session_id).all()

        rows = []
        for c in changes:
            record = Releases.query.filter_by(job=c.job, release=c.release).first()
            current = _serialize_field_current(record, c.field) if record else None
            new_for_compare = _serialize_new_value_for_compare(c.field, c.new_value)

            if record is None:
                conflict = True
            else:
                differs_from_baseline = not _values_equal(c.field, current, c.baseline_value)
                differs_from_new = not _values_equal(c.field, current, new_for_compare)
                conflict = differs_from_baseline and differs_from_new

            rows.append({
                'id': c.id,
                'job': c.job,
                'release': c.release,
                'field': c.field,
                'baseline_value': c.baseline_value,
                'new_value': c.new_value,
                'current_value': current,
                'conflict': conflict,
                'status': c.status,
                'error': c.error,
                'applied_at': c.applied_at.isoformat() if c.applied_at else None,
            })

        return {
            'session': session.to_dict(),
            'changes': rows,
        }

    @staticmethod
    def apply(session_id: int, source: str = "Brain") -> dict:
        # Lock the session row to prevent concurrent apply/discard calls.
        session = (
            db.session.query(StashSession)
            .filter_by(id=session_id)
            .with_for_update()
            .first()
        )
        if session is None:
            raise SessionNotFoundError(f"StashSession {session_id} not found")
        if session.status != 'active':
            raise SessionNotActiveError(
                f"Session {session_id} is not active (status={session.status})"
            )

        changes = (
            StashedJobChange.query.filter_by(session_id=session_id).all()
        )

        # Sort by (job, release, field_order). This groups changes per row and
        # applies fields in a deterministic, dependency-aware order.
        changes.sort(
            key=lambda c: (c.job, c.release, _FIELD_ORDER_MAP.get(c.field, 99))
        )

        applied = 0
        no_op = 0
        conflicts = 0
        failed = 0
        already = 0

        for change in changes:
            if change.applied_at is not None:
                # Idempotent skip
                already += 1
                continue

            record = Releases.query.filter_by(
                job=change.job, release=change.release,
            ).first()
            if record is None:
                change.status = 'failed'
                change.error = f'Release {change.job}-{change.release} not found'
                failed += 1
                continue

            current = _serialize_field_current(record, change.field)
            new_for_compare = _serialize_new_value_for_compare(change.field, change.new_value)

            # If already matches the queued new value, nothing to do.
            if _values_equal(change.field, current, new_for_compare):
                change.status = 'no_op'
                change.applied_at = datetime.utcnow()
                change.error = None
                no_op += 1
                continue

            # Conflict: DB has drifted away from both baseline and our new value.
            if (
                not _values_equal(change.field, current, change.baseline_value)
                and not _values_equal(change.field, current, new_for_compare)
            ):
                change.status = 'conflict'
                change.error = 'Value changed outside this session'
                conflicts += 1
                continue

            apply_change(change, source=source)
            if change.status == 'applied':
                applied += 1
            else:
                failed += 1

        # Decide session status before commit.
        session.ended_at = datetime.utcnow()
        if failed == 0 and conflicts == 0:
            session.status = 'applied'
        else:
            session.status = 'partial'

        db.session.commit()

        # Run scheduling cascade exactly once, after all edits committed.
        try:
            from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
            recalculate_all_jobs_scheduling(stage_group='FABRICATION')
        except Exception as e:
            logger.error(f"Scheduling cascade failed after stash apply: {e}", exc_info=True)

        logger.info(
            f"Stash session {session_id} applied: "
            f"applied={applied} no_op={no_op} conflicts={conflicts} "
            f"failed={failed} already={already}"
        )

        return {
            'session': session.to_dict(),
            'summary': {
                'applied': applied,
                'no_op': no_op,
                'conflicts': conflicts,
                'failed': failed,
                'already_applied': already,
            },
        }

    @staticmethod
    def discard(session_id: int) -> StashSession:
        session = (
            db.session.query(StashSession)
            .filter_by(id=session_id)
            .with_for_update()
            .first()
        )
        if session is None:
            raise SessionNotFoundError(f"StashSession {session_id} not found")
        if session.status != 'active':
            raise SessionNotActiveError(
                f"Session {session_id} is not active (status={session.status})"
            )

        session.status = 'discarded'
        session.ended_at = datetime.utcnow()
        db.session.commit()
        logger.info(f"Stash session {session_id} discarded")
        return session
