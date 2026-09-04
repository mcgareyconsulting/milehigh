"""
@milehigh-header
schema_version: 1
purpose: Encapsulate assigning an installer team to a release (DB write, event, and QUEUEING the mirror Trello card's move + date bar onto the outbox) as a single command object.
exports:
  AssignInstallerCommand: Dataclass command that sets Releases.installer and queues the mirror-card sync
  AssignInstallerResult: Dataclass result with event_id and installer
imports_from: [app.models, app.services.job_event_service, app.services.outbox_service, app.brain.job_log.scheduling.calculator]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - installer is stored as the Trello list name; empty/None clears it and moves the mirror back to Unassigned
  - The mirror move + date bar are DEFERRED to TrelloOutbox (action 'assign_installer'), never called
    inline. The DB write commits immediately; the event stays open until the outbox delivers it, so a
    failed mirror update is retried with backoff and finally logged as an ERROR rather than swallowed.
  - comp_eta is computed here, synchronously — it is DB truth the Timeline reads, not a Trello concern
  - Deduplicated events raise ValueError, matching UpdateStartInstallCommand
  - Does not run a scheduling recalc (installer does not affect scheduling)
  - parent_event_id links this event to the one that caused it, so the undo endpoint reverts both
    halves of a single gesture (a timeline drag writes date + installer) as one bundle
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger
from app.services.outbox_service import OutboxService
from app.brain.job_log.scheduling.calculator import calculate_install_complete_date

logger = get_logger(__name__)


@dataclass
class AssignInstallerResult:
    job_id: int
    release: str
    event_id: int
    installer: Optional[str]
    status: str = "success"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "release": self.release,
            "event_id": self.event_id,
            "installer": self.installer,
            "status": self.status,
        }


@dataclass
class AssignInstallerCommand:
    """Assign (or clear) the installer team for a job-release combination."""
    job_id: int
    release: str
    installer: Optional[str]
    source: str = "Brain"
    undone_event_id: Optional[int] = None
    # Set when this assignment is one half of a larger action — a Timeline drag writes the date and
    # the installer in one gesture, and undoing either half alone would leave the release half-moved.
    # The undo endpoint collects events carrying a parent_event_id and reverts the whole bundle.
    parent_event_id: Optional[int] = None

    def execute(self) -> AssignInstallerResult:
        job_record: Releases = Releases.query.filter_by(
            job=self.job_id, release=self.release
        ).first()
        if not job_record:
            logger.debug("job_not_found", job=self.job_id, release=self.release)
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        new_installer = self.installer.strip() if self.installer and self.installer.strip() else None
        old_installer = job_record.installer

        event_payload = {'from': old_installer, 'to': new_installer}
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id
        if self.parent_event_id is not None:
            event_payload['parent_event_id'] = self.parent_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_installer',
            source=self.source,
            payload=event_payload,
        )
        if event is None:
            logger.debug(
                "installer_update_deduplicated",
                job=self.job_id,
                release=self.release,
            )
            raise ValueError("Event already exists")

        job_record.installer = new_installer
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source

        # comp_eta is DB truth the Timeline reads immediately, so it is computed HERE, synchronously
        # — only the Trello push is deferred. Assigning a crew to a dated release fixes the install
        # window; the mirror's date bar is just a rendering of it.
        if new_installer and job_record.start_install and not job_record.comp_eta:
            job_record.comp_eta = calculate_install_complete_date(
                job_record.start_install, job_record.install_hrs, job_record.num_guys
            )

        # Mirror-card work (move into the crew's list, seed its date bar) goes through the outbox
        # rather than blocking this request on ~5 Trello round-trips that used to be swallowed on
        # failure. The event stays OPEN until OutboxService delivers it and closes it, so a lost
        # mirror update is now a retried, then ERROR-logged, outbox row instead of a silent warning.
        if job_record.trello_card_id:
            OutboxService.add(
                destination='trello',
                action='assign_installer',
                event_id=event.id,
            )
        else:
            # Nothing to deliver — close the event now.
            logger.debug(
                "mirror_move_skipped_no_card",
                job=self.job_id,
                release=self.release,
            )
            JobEventService.close(event.id)

        db.session.commit()

        logger.info(
            "installer_assigned",
            release_id=job_record.id,
            job=self.job_id,
            release=self.release,
            event_id=event.id,
            installer=new_installer,
        )

        return AssignInstallerResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            installer=new_installer,
        )
