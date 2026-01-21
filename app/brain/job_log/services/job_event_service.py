# app/brain/job_log/features/fab_order/services/job_event_service.py
from datetime import datetime
import hashlib
import json
from typing import Optional

from app.models import JobEvents, db  # your actual SQLAlchemy model
from app.brain.job_log.job_events import JobEvent
from app.logging_config import get_logger

logger = get_logger(__name__)


class JobEventService:
    """Service for creating and managing job events (deduplication, logging, DB)"""

    def __init__(self, session=db.session):
        self.session = session
        self.logger = logger

    def create(
        self,
        job: int,
        release: str,
        action: str,
        source: str,
        payload: dict
    ) -> Optional[JobEvent]:
        """
        Create a new JobEvent with deduplication.
        Returns JobEvent dataclass if created, None if duplicate.
        """

        # 1️⃣ Generate payload hash for deduplication
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        hash_string = f"{action}:{job}:{release}:{payload_json}"
        payload_hash = hashlib.sha256(hash_string.encode("utf-8")).hexdigest()

        # 2️⃣ Check for duplicates
        existing = self.session.query(JobEvents).filter_by(payload_hash=payload_hash).first()
        if existing:
            self.logger.info("Duplicate event detected", extra={
                "job": job,
                "release": release,
                "action": action,
                "existing_event_id": existing.id
            })
            return None

        # 3️⃣ Create DB object
        db_event = JobEvents(
            job=job,
            release=release,
            action=action,
            source=source,
            payload=payload,
            payload_hash=payload_hash,
            created_at=datetime.utcnow()
        )

        self.session.add(db_event)
        self.session.flush()  # assign ID

        self.logger.info(f"Job event created: {db_event.id}", extra={
            "job": job, "release": release, "action": action
        })

        # 4️⃣ Return domain dataclass
        return JobEvent(
            id=db_event.id,
            job=db_event.job,
            release=db_event.release,
            action=db_event.action,
            source=db_event.source,
            payload=db_event.payload,
            payload_hash=db_event.payload_hash,
            created_at=db_event.created_at,
            applied_at=db_event.applied_at
        )

    def close(self, event_id: int):
        """Mark event as applied"""
        db_event = self.session.query(JobEvents).get(event_id)
        if db_event:
            db_event.applied_at = datetime.utcnow()
            self.logger.debug(f"Event {event_id} marked as applied")
        else:
            self.logger.warning(f"Attempted to close non-existent event {event_id}")
