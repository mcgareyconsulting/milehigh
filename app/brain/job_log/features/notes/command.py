"""
@milehigh-header
schema_version: 1
purpose: Encapsulate the notes update workflow (DB write, event creation, Trello outbox) as a single command object.
exports:
  UpdateNotesCommand: Dataclass command that executes a notes update with all side effects
  NotesUpdateResult: Dataclass result with event_id and notes
imports_from: [app.models, app.services.outbox_service, app.services.job_event_service]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - Empty / whitespace-only notes are stored as NULL in the DB
  - Trello comment outbox is queued only when the card exists AND notes is non-empty
  - Deduplicated events raise ValueError, matching UpdateStageCommand / UpdateFabOrderCommand
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.models import Releases, db
from app.services.outbox_service import OutboxService
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class NotesUpdateResult:
    job_id: int
    release: str
    event_id: int
    notes: Optional[str]
    status: str = "success"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "release": self.release,
            "event_id": self.event_id,
            "notes": self.notes,
            "status": self.status,
        }


@dataclass
class UpdateNotesCommand:
    """
    Command to update the notes for a job-release combination.

    Mirrors the pre-extraction /update-notes route:
      1. Fetch Releases row.
      2. Create `update_notes` event (raises ValueError on dedup hit).
      3. Overwrite notes column (empty string → NULL).
      4. Queue Trello outbox `update_notes` if card exists and notes non-empty.
      5. Commit.
    """
    job_id: int
    release: str
    notes: str
    source: str = "Brain"
    source_of_update: str = "Brain"
    undone_event_id: Optional[int] = None

    def execute(self) -> NotesUpdateResult:
        notes = "" if self.notes is None else str(self.notes).strip()

        job_record: Releases = Releases.query.filter_by(
            job=self.job_id, release=self.release
        ).first()
        if not job_record:
            logger.warning(f"Job not found: {self.job_id}-{self.release}")
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        old_notes = job_record.notes

        event_payload = {'from': old_notes, 'to': notes}
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_notes',
            source=self.source,
            payload=event_payload,
        )
        if event is None:
            logger.info(
                f"Event already exists for job {self.job_id}-{self.release} notes update"
            )
            raise ValueError("Event already exists")

        job_record.notes = notes if notes else None
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        outbox_item_created = False
        if job_record.trello_card_id and notes:
            try:
                OutboxService.add(
                    destination='trello',
                    action='update_notes',
                    event_id=event.id,
                )
                outbox_item_created = True
                logger.info(
                    f"Outbox item created for Trello notes update "
                    f"(job {self.job_id}-{self.release})"
                )
            except Exception as outbox_error:
                logger.error(
                    f"Failed to create outbox for event {event.id}: {outbox_error}",
                    exc_info=True,
                )
        else:
            if not job_record.trello_card_id:
                logger.warning(
                    f"Job {self.job_id}-{self.release} has no trello_card_id, "
                    f"skipping Trello update",
                    extra={'job': self.job_id, 'release': self.release},
                )
            elif not notes:
                logger.info(
                    f"Notes is empty for job {self.job_id}-{self.release}, "
                    f"skipping Trello comment"
                )

        if not outbox_item_created:
            JobEventService.close(event.id)

        db.session.commit()

        logger.info(
            "update_notes completed successfully",
            extra={'job': self.job_id, 'release': self.release, 'event_id': event.id},
        )

        return NotesUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            notes=job_record.notes,
        )
