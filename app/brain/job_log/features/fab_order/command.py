# app/brain/job_log/features/fab_order/command.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Job, db
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
    source: str = "user"  # Matches route default ('user' for Brain API)
    source_of_update: str = "Brain"  # Matches route's hardcoded value

    def execute(self) -> FabOrderUpdateResult:
        """
        Execute the fab_order update.
        
        Returns:
            FabOrderUpdateResult with job_id, release, event_id, fab_order, and status
            
        Raises:
            ValueError: If job not found or event already exists (deduplicated)
        """
        # 1️⃣ Fetch job record
        job_record: Job = Job.query.filter_by(job=self.job_id, release=self.release).first()
        if not job_record:
            logger.warning(f"Job not found: {self.job_id}-{self.release}")
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        # Capture old state for payload
        old_fab_order = job_record.fab_order

        # 2️⃣ Create event (handles deduplication, logging internally)
        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_fab_order',
            source=self.source,
            payload={
                'from': old_fab_order,
                'to': self.fab_order
            }
        )

        # Check if event was deduplicated
        if event is None:
            logger.info(f"Event already exists for job {self.job_id}-{self.release} fab_order update")
            raise ValueError("Event already exists")
        
        # 3️⃣ Update job fields
        job_record.fab_order = self.fab_order
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        # 4️⃣ Add Trello update to outbox and process immediately
        outbox_item_created = False
        
        if job_record.trello_card_id:
            try:
                # Create outbox item
                outbox_item = OutboxService.add(
                    destination='trello',
                    action='update_fab_order',
                    event_id=event.id
                )
                outbox_item_created = True
                
                # Try to process immediately for live updates
                try:
                    if OutboxService.process_item(outbox_item):
                        logger.info(f"Trello fab_order update processed immediately for job {self.job_id}-{self.release}")
                except Exception as process_error:
                    logger.error(f"Error during immediate processing of outbox {outbox_item.id}: {process_error}", exc_info=True)
                    
            except Exception as outbox_error:
                logger.error(f"Failed to create outbox for event {event.id}: {outbox_error}", exc_info=True)
        else:
            logger.warning(
                f"Job {self.job_id}-{self.release} has no trello_card_id, skipping Trello update",
                extra={'job': self.job_id, 'release': self.release}
            )
        
        # 5️⃣ Close event only if no outbox item was created
        if not outbox_item_created:
            JobEventService.close(event.id)
        
        # 6️⃣ Commit all changes
        db.session.commit()
        
        logger.info(f"update_fab_order completed successfully", extra={
            'job': self.job_id,
            'release': self.release,
            'event_id': event.id
        })
        
        # 7️⃣ Return structured result
        return FabOrderUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            fab_order=self.fab_order,
            status="success"
        )
