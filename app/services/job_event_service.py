"""
@milehigh-header
schema_version: 1
purpose: Creates deduplicated job events using time-bucketed payload hashing so concurrent webhook deliveries don't produce duplicate records.
exports:
  JobEventService: Static methods create(), close(), create_and_close() for the event lifecycle
  DEDUP_WINDOW_SECONDS: Dedup bucket width (30s) — events with identical payload hash within this window are dropped
imports_from: [app/models, app/auth/utils, app/trello/helpers, app/logging_config]
imported_by: [app/trello/sync.py, app/services/outbox_service.py, app/brain/job_log/routes.py, app/brain/job_log/features/fab_order/command.py]
invariants:
  - Dedup window is 30 seconds (DEDUP_WINDOW_SECONDS); events with the same payload hash within that window are dropped via DB unique constraint.
  - create() uses a SAVEPOINT (begin_nested) so IntegrityError on duplicate does not roll back the caller's transaction.
  - Brain source resolves internal_user_id via get_current_user(); Trello source resolves via trello_id lookup — other sources get None.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
from datetime import datetime
from app.logging_config import get_logger
from app.auth.utils import get_current_user

logger = get_logger(__name__)

DEDUP_WINDOW_SECONDS = 30

class JobEventService:
    """Service for managing job events"""

    @staticmethod
    def create(job, release, action, source, payload, external_user_id=None):
        """
        Create a new job event with deduplication.

        Args:
            job: Job number
            release: Release string
            action: Action string
            source: Base source string (e.g., 'Brain', 'Trello', 'Excel', 'Procore')
            payload: Event payload dict
            external_user_id: Optional external user id (e.g. Trello member id, Procore user id)

        Returns:
            JobEvents object if created
            None if duplicate detected
        """
        from app.models import ReleaseEvents, db
        from sqlalchemy.exc import IntegrityError
        import json
        import hashlib
        import time

        # Resolve internal_user_id: Brain uses get_current_user(); Trello resolves via users.trello_id
        internal_user_id = None
        if source == "Brain":
            user = get_current_user()
            internal_user_id = user.id if user else None
        elif source == "Trello" and external_user_id:
            from app.trello.helpers import resolve_internal_user_id_from_trello
            internal_user_id = resolve_internal_user_id_from_trello(external_user_id)

        # Generate payload hash for deduplication (time-bucketed)
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        bucket = int(time.time() // DEDUP_WINDOW_SECONDS)
        hash_string = f"{action}:{job}:{release}:{payload_json}:{bucket}"
        payload_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()

        # Create event
        logger.info(f"Creating job event", extra={
            'job': job,
            'release': release,
            'action': action,
            'source': source,
            'external_user_id': external_user_id,
            'internal_user_id': internal_user_id,
        })

        event = ReleaseEvents(
            job=job,
            release=release,
            action=action,
            payload=payload,
            payload_hash=payload_hash,
            source=source,
            internal_user_id=internal_user_id,
            external_user_id=external_user_id,
            created_at=datetime.utcnow()
        )

        try:
            with db.session.begin_nested():  # SAVEPOINT — protects caller's pending changes
                db.session.add(event)
                db.session.flush()
        except IntegrityError:
            logger.info("Duplicate event detected (DB constraint)", extra={
                'job': job,
                'release': release,
                'action': action,
                'payload_hash': payload_hash,
            })
            return None

        logger.info(f"Job event created: {event.id}")
        return event

    @staticmethod
    def close(event_id):
        """Mark event as applied"""
        from app.models import ReleaseEvents, db

        event = ReleaseEvents.query.get(event_id)
        if event:
            event.applied_at = datetime.utcnow()
            logger.debug(f"Event {event_id} marked as applied")
        else:
            logger.warning(f"Attempted to close non-existent event {event_id}")

    @staticmethod
    def create_and_close(job, release, action, source, payload, external_user_id=None):
        """Create a job event and immediately mark it as applied.

        Use this for DB-only changes that have no async outbox step.
        Returns the event if created, None if deduplicated.
        """
        event = JobEventService.create(
            job=job, release=release, action=action,
            source=source, payload=payload,
            external_user_id=external_user_id,
        )
        if event:
            JobEventService.close(event.id)
        return event
