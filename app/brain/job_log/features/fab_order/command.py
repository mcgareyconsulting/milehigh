"""
@milehigh-header
schema_version: 1
purpose: Encapsulate the full fab_order update workflow (DB write, event creation, outbox queuing, scheduling recalc) as a single command object.
exports:
  UpdateFabOrderCommand: Dataclass command that executes a fab_order update with all side effects
imports_from: [app.models, app.brain.job_log.features.fab_order.results, app.services.outbox_service, app.services.job_event_service, app.api.helpers, app.brain.job_log.scheduling.service]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - Fixed-tier stages always override the requested fab_order with their tier value
  - Deduplicated events raise ValueError, not silently succeed
  - Scheduling recalculation failure is logged but does not roll back the update
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
# app/brain/job_log/features/fab_order/command.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Releases, db
from app.brain.job_log.features.fab_order.results import FabOrderUpdateResult
from app.services.outbox_service import OutboxService
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class UpdateFabOrderCommand:
    """
    Command to update the fab_order for a job-release combination.
    
    Matches the behavior of the update_fab_order route:
    - Updates the Job record in the DB
    - Creates a JobEvent with deduplication
    - Adds an OutboxItem for Trello (if card exists)
    - Processes outbox immediately for live updates
    - Closes event if no outbox was created
    - Commits all changes
    """
    job_id: int
    release: str
    fab_order: Optional[float]
    source: str = "Brain"  # Will be formatted as 'Brain:username' automatically
    source_of_update: str = "Brain"  # Matches route's hardcoded value
    # When True, skip the final recalculate_all_jobs_scheduling call — useful when
    # the caller is batching multiple updates and will run the cascade once at the end.
    defer_cascade: bool = False

    def execute(self) -> FabOrderUpdateResult:
        """
        Execute the fab_order update.
        
        Returns:
            FabOrderUpdateResult with job_id, release, event_id, fab_order, and status
            
        Raises:
            ValueError: If job not found or event already exists (deduplicated)
        """
        # 1️⃣ Fetch job record
        job_record: Releases = Releases.query.filter_by(job=self.job_id, release=self.release).first()
        if not job_record:
            logger.warning(f"Job not found: {self.job_id}-{self.release}")
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        # Capture old state for payload
        import math
        old_fab_order = job_record.fab_order

        # Ensure old_fab_order is not NaN for JSON serialization
        if isinstance(old_fab_order, float) and math.isnan(old_fab_order):
            logger.warning(f"Job {self.job_id}-{self.release} has NaN fab_order, converting to None")
            old_fab_order = None

        # 1b. Fixed-tier guard: stages with auto-assigned fab_order
        from app.api.helpers import get_fixed_tier
        tier = get_fixed_tier(job_record.stage)
        if tier is not None:
            self.fab_order = tier
            logger.info(
                f"Job {self.job_id}-{self.release} is fixed tier {tier} "
                f"(stage={job_record.stage}), overriding fab_order to {tier}"
            )

        # 2️⃣ Create event for the current job (handles deduplication, logging internally)
        # Ensure payload values are valid (not NaN) - convert to None if needed
        payload_from = None if (isinstance(old_fab_order, float) and math.isnan(old_fab_order)) else old_fab_order
        payload_to = None if (self.fab_order is not None and isinstance(self.fab_order, float) and math.isnan(self.fab_order)) else self.fab_order
        
        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_fab_order',
            source=self.source,
            payload={
                'from': payload_from,
                'to': payload_to
            }
        )

        # Check if event was deduplicated
        if event is None:
            logger.info(f"Event already exists for job {self.job_id}-{self.release} fab_order update")
            raise ValueError("Event already exists")
        
        # 4️⃣ Update job fields
        job_record.fab_order = self.fab_order
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        # 5️⃣ Queue outbox item for Trello fab_order sync (event closed by OutboxService on success)
        if job_record.trello_card_id:
            OutboxService.add(
                destination='trello',
                action='update_fab_order',
                event_id=event.id
            )
        else:
            # No Trello card — close event immediately
            JobEventService.close(event.id)
        
        # 7️⃣ Commit all DB changes first (this is the critical operation)
        db.session.commit()

        # 7b. Recalculate scheduling for fab stage (fab_order affects hours_in_front → start_install)
        if not self.defer_cascade:
            try:
                from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
                recalculate_all_jobs_scheduling(stage_group='FABRICATION')
            except Exception as e:
                logger.error(f"Scheduling recalculation failed after fab_order update: {e}", exc_info=True)

        logger.info(f"update_fab_order completed successfully", extra={
            'job': self.job_id,
            'release': self.release,
            'event_id': event.id
        })
        
        # 8️⃣ Return structured result
        return FabOrderUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            fab_order=self.fab_order,
            status="success"
        )
