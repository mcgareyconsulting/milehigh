"""
@milehigh-header
schema_version: 1
purpose: Encapsulate the hard-date start_install update workflow (DB write, event creation, Trello due-date push, scheduling recalc) as a single command object.
exports:
  UpdateStartInstallCommand: Dataclass command that executes a start_install update with all side effects
  StartInstallUpdateResult: Dataclass result with event_id and start_install
imports_from: [app.models, app.services.job_event_service, app.brain.trello.helpers (update_trello_card)]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - Hard date sets start_install_formulaTF=False and clears start_install_formula
  - Trello due-date push is synchronous (matches the pre-extraction route behavior)
  - Deduplicated events raise ValueError, matching UpdateStageCommand / UpdateFabOrderCommand
  - This command does NOT cover the `clear_hard_date` flow — that remains in the route as it
    writes a different action ('clear_hard_date') and is not undoable.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class StartInstallUpdateResult:
    job_id: int
    release: str
    event_id: int
    start_install: Optional[date]
    is_hard_date: bool
    status: str = "success"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "release": self.release,
            "event_id": self.event_id,
            "start_install": self.start_install.isoformat() if self.start_install else None,
            "is_hard_date": self.is_hard_date,
            "status": self.status,
        }


@dataclass
class UpdateStartInstallCommand:
    """
    Command to set a hard-date start_install for a job-release combination.

    Mirrors the hard-date branch of /update-start-install:
      1. Fetch Releases row.
      2. Create `update_start_install` event (raises ValueError on dedup hit).
      3. Set start_install + clear formula fields.
      4. Push Trello due date synchronously if card exists.
      5. Commit; run scheduling cascade.
    """
    job_id: int
    release: str
    start_install: Optional[date]
    is_hard_date: bool = True
    source: str = "Brain"
    source_of_update: str = "Brain"
    undone_event_id: Optional[int] = None

    def execute(self) -> StartInstallUpdateResult:
        # Lazy import — avoid circular with routes module.
        from app.brain.job_log.routes import update_trello_card

        job_record: Releases = Releases.query.filter_by(
            job=self.job_id, release=self.release
        ).first()
        if not job_record:
            logger.warning(f"Job not found: {self.job_id}-{self.release}")
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        old_start_install = job_record.start_install

        event_payload = {
            'from': old_start_install.isoformat() if old_start_install else None,
            'to': self.start_install.isoformat() if self.start_install else None,
            'is_hard_date': self.is_hard_date,
        }
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_start_install',
            source=self.source,
            payload=event_payload,
        )
        if event is None:
            logger.info(
                f"Event already exists for job {self.job_id}-{self.release} start_install update"
            )
            raise ValueError("Event already exists")

        job_record.start_install = self.start_install
        job_record.start_install_formula = None
        job_record.start_install_formulaTF = False
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        if job_record.trello_card_id:
            try:
                update_trello_card(
                    card_id=job_record.trello_card_id,
                    new_due_date=self.start_install,
                    clear_due_date=(self.start_install is None),
                )
                logger.info(
                    f"Trello card due date updated for job {self.job_id}-{self.release} "
                    f"(start_install sent as due date)"
                )
            except Exception as trello_error:
                logger.error(
                    f"Failed to update Trello card due date for job "
                    f"{self.job_id}-{self.release}: {trello_error}",
                    exc_info=True,
                )
        else:
            logger.warning(
                f"Job {self.job_id}-{self.release} has no trello_card_id, skipping Trello update",
                extra={'job': self.job_id, 'release': self.release},
            )

        JobEventService.close(event.id)
        db.session.commit()

        try:
            from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
            recalculate_all_jobs_scheduling(stage_group='FABRICATION')
        except Exception as cascade_error:
            logger.error(
                f"Scheduling cascade failed after hard-date update: {cascade_error}",
                exc_info=True,
            )

        logger.info(
            "update_start_install completed successfully",
            extra={'job': self.job_id, 'release': self.release, 'event_id': event.id},
        )

        return StartInstallUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            start_install=self.start_install,
            is_hard_date=self.is_hard_date,
        )
