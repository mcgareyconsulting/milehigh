"""
@milehigh-header
schema_version: 1
purpose: Encapsulate the ship_date update workflow (DB write + event creation) as a single command object. A lighter sibling of UpdateStartInstallCommand — no Trello push, no comp_eta recompute, no scheduling recalc (start_install remains the scheduling driver).
exports:
  UpdateShipDateCommand: Dataclass command that executes a ship_date update
  ShipDateUpdateResult: Dataclass result with event_id and ship_date
imports_from: [app.models, app.services.job_event_service]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - ship_date is a plain hard date; its color follows start_install_no_color (no separate flag)
  - Deduplicated events raise ValueError, matching UpdateStartInstallCommand
  - Does NOT push to Trello and does NOT affect comp_eta / scheduling
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ShipDateUpdateResult:
    job_id: int
    release: str
    event_id: int
    ship_date: Optional[date]
    status: str = "success"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "release": self.release,
            "event_id": self.event_id,
            "ship_date": self.ship_date.isoformat() if self.ship_date else None,
            "status": self.status,
        }


@dataclass
class UpdateShipDateCommand:
    """
    Command to set (or clear, with ship_date=None) a job-release's ship_date.

    Flow:
      1. Fetch Releases row.
      2. Create `update_ship_date` event (raises ValueError on dedup hit).
      3. Set ship_date.
      4. Commit.
    Unlike start_install, this pushes nothing to Trello and touches no scheduling.
    """
    job_id: int
    release: str
    ship_date: Optional[date]
    source: str = "Brain"
    source_of_update: str = "Brain"
    undone_event_id: Optional[int] = None

    def execute(self) -> ShipDateUpdateResult:
        job_record: Releases = Releases.query.filter_by(
            job=self.job_id, release=self.release
        ).first()
        if not job_record:
            logger.debug("job_not_found", job=self.job_id, release=self.release)
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        old_ship_date = job_record.ship_date

        event_payload = {
            'from': old_ship_date.isoformat() if old_ship_date else None,
            'to': self.ship_date.isoformat() if self.ship_date else None,
        }
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_ship_date',
            source=self.source,
            payload=event_payload,
        )
        if event is None:
            logger.debug(
                "ship_date_update_deduplicated",
                job=self.job_id,
                release=self.release,
            )
            raise ValueError("Event already exists")

        job_record.ship_date = self.ship_date
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        JobEventService.close(event.id)
        db.session.commit()

        logger.info(
            "ship_date_updated",
            release_id=job_record.id,
            job=self.job_id,
            release=self.release,
            event_id=event.id,
            ship_date=self.ship_date.isoformat() if self.ship_date else None,
        )

        return ShipDateUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            ship_date=self.ship_date,
        )
