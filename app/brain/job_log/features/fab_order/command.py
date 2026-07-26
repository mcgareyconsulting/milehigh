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
    # When True, skip the final recalculate_all_jobs_scheduling call — used by
    # the /brain/events/<id>/undo bundling path so the cascade runs once after
    # the parent + linked children all revert.
    defer_cascade: bool = False
    # When set, merged into the event payload as `undone_event_id`. Used by the
    # /brain/events/<id>/undo endpoint to link the undo event to its source and
    # perturb the dedup hash so undo-the-undo within 30s doesn't collide.
    undone_event_id: Optional[int] = None

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
            logger.debug("job_not_found", job=self.job_id, release=self.release)
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        # Capture old state for payload
        import math
        old_fab_order = job_record.fab_order

        # Ensure old_fab_order is not NaN for JSON serialization
        if isinstance(old_fab_order, float) and math.isnan(old_fab_order):
            logger.warning("fab_order_nan_coerced", job=self.job_id, release=self.release)
            old_fab_order = None

        # 1b. Fixed-tier guard: stages with auto-assigned fab_order
        from app.api.helpers import get_fixed_tier
        tier = get_fixed_tier(job_record.stage)
        if tier is not None:
            self.fab_order = tier
            logger.debug(
                "fab_order_fixed_tier_override",
                job=self.job_id,
                release=self.release,
                stage=job_record.stage,
                tier=tier,
            )

        # 1c. Complete is terminal — no ordering. Always force fab_order to None.
        if (job_record.stage or "").strip().lower() == "complete":
            if self.fab_order is not None:
                logger.debug(
                    "fab_order_forced_null_complete",
                    job=self.job_id,
                    release=self.release,
                    old=self.fab_order,
                )
            self.fab_order = None

        # 2️⃣ Create event for the current job (handles deduplication, logging internally)
        # Ensure payload values are valid (not NaN) - convert to None if needed
        payload_from = None if (isinstance(old_fab_order, float) and math.isnan(old_fab_order)) else old_fab_order
        payload_to = None if (self.fab_order is not None and isinstance(self.fab_order, float) and math.isnan(self.fab_order)) else self.fab_order
        
        event_payload = {'from': payload_from, 'to': payload_to}
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_fab_order',
            source=self.source,
            payload=event_payload,
        )

        # Check if event was deduplicated
        if event is None:
            logger.debug(
                "fab_order_update_deduplicated",
                job=self.job_id,
                release=self.release,
            )
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
                logger.error(
                    "scheduling_recalc_failed",
                    job=self.job_id,
                    release=self.release,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )

        logger.info(
            "fab_order_updated",
            release_id=job_record.id,
            job=self.job_id,
            release=self.release,
            event_id=event.id,
            fab_order=self.fab_order,
        )
        
        # 8️⃣ Return structured result
        return FabOrderUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            fab_order=self.fab_order,
            status="success"
        )
