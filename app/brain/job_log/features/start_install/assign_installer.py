"""
@milehigh-header
schema_version: 1
purpose: Encapsulate assigning an installer team to a release (DB write, event, and moving the release's mirror Trello card into the matching installer list) as a single command object.
exports:
  AssignInstallerCommand: Dataclass command that sets Releases.installer and moves the mirror card
  AssignInstallerResult: Dataclass result with event_id and installer
imports_from: [app.models, app.config, app.services.job_event_service, app.trello.api (move_mirror_card, get_list_by_name)]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - installer is stored as the Trello list name; empty/None clears it and moves the mirror back to Unassigned
  - Mirror card move is synchronous and best-effort (failure is logged, DB write still commits)
  - Deduplicated events raise ValueError, matching UpdateStartInstallCommand
  - Does not run a scheduling recalc (installer does not affect scheduling)
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Releases, db
from app.config import Config
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger
from app.trello.api import move_mirror_card, get_list_by_name, set_mirror_date_range
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

    def execute(self) -> AssignInstallerResult:
        job_record: Releases = Releases.query.filter_by(
            job=self.job_id, release=self.release
        ).first()
        if not job_record:
            logger.warning(f"Job not found: {self.job_id}-{self.release}")
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        new_installer = self.installer.strip() if self.installer and self.installer.strip() else None
        old_installer = job_record.installer

        event_payload = {'from': old_installer, 'to': new_installer}
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_installer',
            source=self.source,
            payload=event_payload,
        )
        if event is None:
            logger.info(
                f"Event already exists for job {self.job_id}-{self.release} installer update"
            )
            raise ValueError("Event already exists")

        job_record.installer = new_installer
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source

        # Resolve the target list: the installer list by name, or Unassigned when cleared.
        if new_installer:
            entry = get_list_by_name(new_installer)
            target_list_id = entry["id"] if entry else None
            if not target_list_id:
                logger.warning(
                    f"No Trello list found matching installer '{new_installer}'; "
                    f"skipping mirror move for job {self.job_id}-{self.release}"
                )
        else:
            target_list_id = Config.UNASSIGNED_CARDS_LIST_ID

        if job_record.trello_card_id and target_list_id:
            try:
                move_mirror_card(job_record.trello_card_id, target_list_id)
                logger.info(
                    f"Mirror card moved for job {self.job_id}-{self.release} "
                    f"(installer={new_installer or 'Unassigned'})"
                )
            except Exception as trello_error:
                logger.error(
                    f"Failed to move mirror card for job {self.job_id}-{self.release}: {trello_error}",
                    exc_info=True,
                )
        elif not job_record.trello_card_id:
            logger.warning(
                f"Job {self.job_id}-{self.release} has no trello_card_id, skipping mirror move",
                extra={'job': self.job_id, 'release': self.release},
            )

        # When assigning to a team (not clearing), seed the mirror card's date bar to
        # [start_install, comp_eta] and remember the mirror's id for inbound write-back.
        if new_installer and job_record.trello_card_id and job_record.start_install:
            comp_eta = job_record.comp_eta or calculate_install_complete_date(
                job_record.start_install, job_record.install_hrs, job_record.num_guys
            )
            if comp_eta and not job_record.comp_eta:
                job_record.comp_eta = comp_eta
            try:
                range_result = set_mirror_date_range(
                    job_record.trello_card_id, job_record.start_install, comp_eta
                )
                if range_result.get("success"):
                    mirror_id = range_result.get("mirror_card_id")
                    if mirror_id:
                        job_record.mirror_trello_card_id = mirror_id
                    logger.info(
                        f"Mirror date range set for job {self.job_id}-{self.release} "
                        f"[{job_record.start_install} -> {comp_eta}]"
                    )
                else:
                    logger.warning(
                        f"Could not set mirror date range for job {self.job_id}-{self.release}: "
                        f"{range_result.get('error')}"
                    )
            except Exception as range_error:
                logger.error(
                    f"Failed to set mirror date range for job {self.job_id}-{self.release}: {range_error}",
                    exc_info=True,
                )

        JobEventService.close(event.id)
        db.session.commit()

        logger.info(
            "update_installer completed successfully",
            extra={'job': self.job_id, 'release': self.release, 'event_id': event.id},
        )

        return AssignInstallerResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            installer=new_installer,
        )
