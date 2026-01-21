# app/brain/job_log/features/fab_order/services/job_outbox_service.py
from datetime import datetime, timedelta
from typing import Optional, List
from app.logging_config import get_logger
from app.brain.job_log.outbox import OutboxItem
from app.models import Outbox, Job, db
from app.services.job_event_service import JobEventService

logger = get_logger(__name__)


class OutboxService:
    """Service for managing outbox items with retry and processing capabilities"""

    @staticmethod
    def add(destination: str, action: str, event_id: int, payload: Optional[dict] = None, max_retries: int = 5) -> OutboxItem:
        """Add a new item to the outbox"""
        now = datetime.utcnow()
        outbox_obj = Outbox(
            event_id=event_id,
            destination=destination,
            action=action,
            payload=payload or {},
            status="pending",
            retry_count=0,
            max_retries=max_retries,
            next_retry_at=now,
            created_at=now
        )
        db.session.add(outbox_obj)
        db.session.flush()

        logger.debug(f"Outbox item created: {outbox_obj.id} for event {event_id}")

        # Return as dataclass
        return OutboxItem(
            id=outbox_obj.id,
            event_id=outbox_obj.event_id,
            destination=outbox_obj.destination,
            action=outbox_obj.action,
            payload=outbox_obj.payload,
            status=outbox_obj.status,
            retry_count=outbox_obj.retry_count,
            max_retries=outbox_obj.max_retries,
            next_retry_at=outbox_obj.next_retry_at,
            created_at=outbox_obj.created_at,
            completed_at=outbox_obj.completed_at,
            error_message=outbox_obj.error_message
        )

    @staticmethod
    def process_item(outbox_item: Outbox) -> bool:
        """
        Process an outbox item. Returns True if processed successfully, False otherwise.
        """
        from app.trello.api import update_trello_card, add_comment_to_trello_card

        # Mark as processing
        outbox_item.status = "processing"
        db.session.commit()

        try:
            event = outbox_item.event
            if not event:
                outbox_item.status = "failed"
                outbox_item.error_message = "No associated event found"
                db.session.commit()
                logger.error(f"Outbox {outbox_item.id}: No event found")
                return False

            job_record = Job.query.filter_by(job=event.job, release=event.release).first()
            if not job_record:
                outbox_item.status = "failed"
                outbox_item.error_message = f"Job {event.job}-{event.release} not found"
                db.session.commit()
                return False

            # Example for Trello fab_order update
            if outbox_item.destination == "trello" and outbox_item.action == "update_fab_order":
                fab_order = event.payload.get("to")
                if job_record.trello_card_id:
                    from app.trello.api import update_card_custom_field_number
                    from app.config import Config as cfg
                    import math

                    try:
                        if fab_order is not None:
                            value = math.ceil(fab_order) if isinstance(fab_order, float) else int(fab_order)
                            success = update_card_custom_field_number(job_record.trello_card_id, cfg.FAB_ORDER_FIELD_ID, value)
                        else:
                            success = True  # Treat clearing as success for now

                        if success:
                            outbox_item.status = "completed"
                            outbox_item.completed_at = datetime.utcnow()
                            outbox_item.error_message = None
                            JobEventService.close(event.id)
                            db.session.commit()
                            logger.info(f"Outbox {outbox_item.id} processed successfully")
                            return True
                        else:
                            raise Exception("Trello update failed")
                    except Exception as e:
                        return OutboxService._handle_failure(outbox_item, e)
                else:
                    return OutboxService._handle_failure(outbox_item, "Job has no trello_card_id")

            # Add other action types here...
            else:
                return OutboxService._handle_failure(outbox_item, f"Unsupported {outbox_item.destination}/{outbox_item.action}")

        except Exception as e:
            return OutboxService._handle_failure(outbox_item, e)

    @staticmethod
    def _handle_failure(outbox_item: Outbox, error: Exception | str) -> bool:
        """Internal helper to handle failure and retries"""
        outbox_item.retry_count += 1
        outbox_item.error_message = str(error)
        now = datetime.utcnow()

        if outbox_item.retry_count < outbox_item.max_retries:
            delay_seconds = 2 ** outbox_item.retry_count
            outbox_item.next_retry_at = now + timedelta(seconds=delay_seconds)
            outbox_item.status = "pending"
            db.session.commit()
            logger.warning(f"Outbox {outbox_item.id} will retry ({outbox_item.retry_count}/{outbox_item.max_retries}): {str(error)[:100]}")
        else:
            outbox_item.status = "failed"
            db.session.commit()
            logger.error(f"Outbox {outbox_item.id} failed after {outbox_item.max_retries} retries: {str(error)[:100]}")
        return False

    @staticmethod
    def process_pending_items(limit: int = 10) -> int:
        """Process pending outbox items ready for retry"""
        now = datetime.utcnow()
        pending_items = Outbox.query.filter(
            Outbox.status == "pending",
            Outbox.next_retry_at <= now
        ).limit(limit).all()

        count = 0
        for item in pending_items:
            if OutboxService.process_item(item):
                count += 1
        logger.debug(f"Processed {count}/{len(pending_items)} pending outbox items")
        return count
