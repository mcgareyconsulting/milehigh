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
    source: str = "Brain"  # Will be formatted as 'Brain:username' automatically
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

        # 2️⃣ Collision detection: Cascade bump - shift all jobs with fab_order >= target value up by 1
        if self.fab_order is not None:
            from sqlalchemy import or_, and_
            # Find all jobs in the same stage_group with fab_order >= target value (excluding current job)
            # We need to bump these jobs up by 1 to make room for the new value
            jobs_to_bump = Job.query.filter(
                Job.stage_group == job_record.stage_group,
                Job.fab_order >= self.fab_order,
                or_(
                    Job.job != self.job_id,
                    Job.release != self.release
                )
            ).order_by(Job.fab_order.desc()).all()
            
            if jobs_to_bump:
                logger.info(
                    f"Collision detected: {len(jobs_to_bump)} job(s) with fab_order >= {self.fab_order} "
                    f"will be bumped up by 1 to make room for job {self.job_id}-{self.release}"
                )
                
                # Process each job that needs to be bumped, starting from highest to lowest
                for job_to_bump in jobs_to_bump:
                    old_bump_value = job_to_bump.fab_order
                    new_bump_value = old_bump_value + 1
                    
                    logger.debug(
                        f"Bumping job {job_to_bump.job}-{job_to_bump.release} "
                        f"from {old_bump_value} to {new_bump_value}"
                    )
                    
                    # Create event for the bumped job
                    bump_event = JobEventService.create(
                        job=job_to_bump.job,
                        release=job_to_bump.release,
                        action='update_fab_order',
                        source=self.source,
                        payload={
                            'from': old_bump_value,
                            'to': new_bump_value,
                            'reason': 'collision_resolution_cascade'
                        }
                    )
                    
                    if bump_event is None:
                        logger.warning(f"Event already exists for bumped job {job_to_bump.job}-{job_to_bump.release}")
                    else:
                        # Update bumped job
                        job_to_bump.fab_order = new_bump_value
                        job_to_bump.last_updated_at = datetime.utcnow()
                        job_to_bump.source_of_update = self.source_of_update
                        
                        # Create outbox item for bumped job if it has a Trello card
                        if job_to_bump.trello_card_id:
                            try:
                                OutboxService.add(
                                    destination='trello',
                                    action='update_fab_order',
                                    event_id=bump_event.id
                                )
                                logger.debug(f"Outbox item created for bumped job {job_to_bump.job}-{job_to_bump.release}")
                            except Exception as outbox_error:
                                logger.error(f"Failed to create outbox for bumped job event {bump_event.id}: {outbox_error}", exc_info=True)
                        else:
                            # Close event if no outbox item was created
                            JobEventService.close(bump_event.id)

        # 3️⃣ Create event for the current job (handles deduplication, logging internally)
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
        
        # 4️⃣ Update job fields
        job_record.fab_order = self.fab_order
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        # 5️⃣ Add Trello update to outbox (async - will be processed by outbox service)
        # DB changes are committed first, then outbox handles Trello updates asynchronously
        # This ensures DB changes are never lost due to Trello API failures
        outbox_item_created = False
        
        if job_record.trello_card_id:
            try:
                # Create outbox item - will be processed asynchronously by outbox service
                OutboxService.add(
                    destination='trello',
                    action='update_fab_order',
                    event_id=event.id
                )
                outbox_item_created = True
                logger.info(f"Outbox item created for Trello fab_order update (job {self.job_id}-{self.release})")
            except Exception as outbox_error:
                # Log error but don't fail the operation - DB update is more important
                logger.error(f"Failed to create outbox for event {event.id}: {outbox_error}", exc_info=True)
        else:
            logger.warning(
                f"Job {self.job_id}-{self.release} has no trello_card_id, skipping Trello update",
                extra={'job': self.job_id, 'release': self.release}
            )
        
        # 6️⃣ Close event only if no outbox item was created
        if not outbox_item_created:
            JobEventService.close(event.id)
        
        # 7️⃣ Commit all DB changes first (this is the critical operation)
        db.session.commit()
        
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
