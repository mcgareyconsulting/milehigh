"""
@milehigh-header
schema_version: 1
purpose: Encapsulate the installer-count (num_guys) update workflow — DB write, event creation, comp_eta recompute and the outbound Trello description sync — as a single command object.
exports:
  UpdateNumGuysCommand: Dataclass command that executes a num_guys update with all side effects
  NumGuysUpdateResult: Dataclass result with event_id, num_guys and the recomputed comp_eta
imports_from: [app.models, app.services.job_event_service, app.brain.job_log.scheduling.calculator, app.trello.api (sync_num_guys_on_card)]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - num_guys is a positive number; 0/negative/non-numeric is rejected by the caller, not coerced here
  - comp_eta is ALWAYS recomputed from (start_install, install_hrs, num_guys) — see the note on the
    recompute below; a release with no start_install keeps comp_eta None
  - The Trello description write covers BOTH cards (primary and mirror), best-effort and synchronous,
    matching UpdateStartInstallCommand's due-date push rather than the outbox path
  - Deduplicated events raise ValueError, matching UpdateStartInstallCommand / UpdateStageCommand

BUG-24. Bill asked for the card-level installer count to be "restored"; there was nothing to
restore. `num_guys` is READ across the app (comp_eta, the hub footnote, the mirror push) but the
only thing that ever WROTE it was the inbound Trello sync parsing it out of a card description.
This is that missing write path, on the Brain side where the schedulers actually work.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger
from app.brain.job_log.scheduling.calculator import calculate_install_complete_date

logger = get_logger(__name__)


@dataclass
class NumGuysUpdateResult:
    job_id: int
    release: str
    event_id: int
    num_guys: Optional[float]
    comp_eta: Optional[object] = None
    status: str = "success"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "release": self.release,
            "event_id": self.event_id,
            "num_guys": self.num_guys,
            "comp_eta": self.comp_eta.isoformat() if self.comp_eta else None,
            "status": self.status,
        }


@dataclass
class UpdateNumGuysCommand:
    """Set the installer headcount for a job-release.

      1. Fetch the Releases row.
      2. Create an `update_num_guys` event (raises ValueError on a dedup hit).
      3. Write num_guys and recompute comp_eta from it.
      4. Push the new count into both Trello card descriptions, best-effort.
      5. Commit.
    """
    job_id: int
    release: str
    num_guys: Optional[float]
    source: str = "Brain"
    source_of_update: str = "Brain"
    undone_event_id: Optional[int] = None
    # Set when this write is one half of a larger gesture, so the undo endpoint reverts the
    # whole bundle rather than half of it. Mirrors AssignInstallerCommand.
    parent_event_id: Optional[int] = None

    def execute(self) -> NumGuysUpdateResult:
        job_record: Releases = Releases.resolve(self.job_id, self.release)
        if not job_record:
            logger.debug("job_not_found", job=self.job_id, release=self.release)
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        old_num_guys = job_record.num_guys
        old_comp_eta = job_record.comp_eta

        event_payload = {
            'from': old_num_guys,
            'to': self.num_guys,
            # comp_eta moves with the crew size, and it is not otherwise recoverable from this
            # event — an undo has to be able to put the bar back exactly where it was.
            'comp_eta_from': old_comp_eta.isoformat() if old_comp_eta else None,
        }
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id
        if self.parent_event_id is not None:
            event_payload['parent_event_id'] = self.parent_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_num_guys',
            source=self.source,
            payload=event_payload,
        )
        if event is None:
            logger.debug(
                "num_guys_update_deduplicated",
                job=self.job_id,
                release=self.release,
            )
            raise ValueError("Event already exists")

        job_record.num_guys = self.num_guys

        # comp_eta is RECOMPUTED, never left to drift: the whole point of editing the crew size is
        # that the install window changes with it, and the Timeline, the install schedule and the
        # mirror bar all read comp_eta rather than deriving it.
        #
        # OPEN, and deliberately decided this way for now (BUG-11, 2026-09-02): a Timeline drag or
        # edge-compress writes comp_eta DIRECTLY, so a card can hold a duration its hours and crew
        # size do not imply. A crew edit here overwrites such a compressed value. That is the
        # package's own wording for BUG-24 ("write num_guys -> recompute comp_eta") and it is the
        # only rule under which the number a scheduler types means anything — but it does mean a
        # hand-compressed bar is lost to a later crew edit. If Bill/Daniel decide a compressed card
        # is pinned instead, the change is here: skip the recompute when comp_eta diverges from the
        # formula and the divergence was a manual compress.
        job_record.comp_eta = calculate_install_complete_date(
            job_record.start_install, job_record.install_hrs, self.num_guys
        )
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        # Until T4 retires the Trello board, the card description is still where the crews read the
        # count, so the Brain's number has to land there or the two disagree. Both cards: the
        # primary is what the shop sees, the mirror is the installer team's own surface and is also
        # what the inbound sync parses back out.
        from app.trello.api import sync_num_guys_on_card
        for card_id, which in (
            (job_record.trello_card_id, 'primary'),
            (job_record.mirror_trello_card_id, 'mirror'),
        ):
            if not card_id:
                continue
            try:
                sync_num_guys_on_card(card_id, job_record.install_hrs, self.num_guys)
            except Exception as trello_error:
                logger.error(
                    "num_guys_description_push_failed",
                    job=self.job_id,
                    release=self.release,
                    card=which,
                    error=str(trello_error),
                    error_type=type(trello_error).__name__,
                    exc_info=True,
                )

        JobEventService.close(event.id)
        db.session.commit()

        logger.info(
            "num_guys_updated",
            release_id=job_record.id,
            job=self.job_id,
            release=self.release,
            event_id=event.id,
            num_guys=self.num_guys,
            comp_eta=job_record.comp_eta.isoformat() if job_record.comp_eta else None,
        )

        return NumGuysUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            num_guys=self.num_guys,
            comp_eta=job_record.comp_eta,
        )
