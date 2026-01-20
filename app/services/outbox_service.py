from datetime import datetime, timedelta
from app.logging_config import get_logger
logger = get_logger(__name__)

class OutboxService:
    """Service for managing outbox items with retry capabilities"""
    
    @staticmethod
    def add(destination, action, event_id):
        """
        Add item to outbox for async processing.
        
        Args:
            destination: 'trello' or 'procore'
            action: 'move_card', 'update_card', etc.
            event_id: Related event ID (foreign key to job_events)
        """
        from app.models import Outbox, db
        from datetime import datetime
        
        outbox_item = Outbox(
            event_id=event_id,
            destination=destination,
            action=action,
            status='pending',
            retry_count=0,
            next_retry_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        
        db.session.add(outbox_item)
        db.session.flush()
        
        logger.debug(f"Outbox item created: {outbox_item.id} for event {event_id}")
        return outbox_item
    
    @staticmethod
    def process_item(outbox_item):
        """
        Process a single outbox item by executing the external API call.
        
        This method:
        1. Derives all necessary data from the associated event
        2. Executes the appropriate API call based on destination and action
        3. Handles retries with exponential backoff on failure
        4. Closes the associated event when processing succeeds
        
        Args:
            outbox_item: Outbox model instance to process
            
        Returns:
            bool: True if processing succeeded, False if it failed (and will retry)
        """
        from app.models import Job, db
        from app.services.job_event_service import JobEventService
        from app.trello.api import update_trello_card, get_list_by_name
        
        # Mark as processing to prevent concurrent processing
        outbox_item.status = 'processing'
        db.session.commit()
        
        try:
            # Get the associated event
            event = outbox_item.event
            if not event:
                logger.error(f"Outbox {outbox_item.id}: no associated event")
                outbox_item.status = 'failed'
                outbox_item.error_message = "No associated event found"
                db.session.commit()
                return False
            
            # Get the job record to derive card_id and other data
            job_record = Job.query.filter_by(job=event.job, release=event.release).first()
            if not job_record:
                logger.error(f"Outbox {outbox_item.id}: Job {event.job}-{event.release} not found")
                outbox_item.status = 'failed'
                outbox_item.error_message = f"Job {event.job}-{event.release} not found"
                db.session.commit()
                return False
            
            # Process based on destination and action
            if outbox_item.destination == 'trello' and outbox_item.action == 'move_card':
                # Derive stage from event payload
                stage = event.payload.get('to')
                if not stage:
                    logger.error(f"Outbox {outbox_item.id}: Event payload missing 'to' field")
                    outbox_item.status = 'failed'
                    outbox_item.error_message = "Event payload missing 'to' field"
                    db.session.commit()
                    return False
                
                # Get card_id from job record
                card_id = job_record.trello_card_id
                if not card_id:
                    logger.warning(f"Outbox {outbox_item.id}: Job {event.job}-{event.release} has no trello_card_id")
                    outbox_item.status = 'failed'
                    outbox_item.error_message = "Job has no trello_card_id"
                    db.session.commit()
                    return False
                
                # Get list_id from stage name
                list_info = get_list_by_name(stage)
                if not list_info or 'id' not in list_info:
                    logger.error(f"Outbox {outbox_item.id}: Could not get list ID for stage '{stage}'")
                    outbox_item.status = 'failed'
                    outbox_item.error_message = f"Could not get list ID for stage: {stage}"
                    db.session.commit()
                    return False
                
                list_id = list_info['id']
                
                # Execute the Trello API call
                try:
                    update_trello_card(card_id, new_list_id=list_id)
                    
                    # Success! Mark outbox item as completed
                    outbox_item.status = 'completed'
                    outbox_item.completed_at = datetime.utcnow()
                    outbox_item.error_message = None
                    db.session.commit()
                    
                    # Close the associated event now that external API call succeeded
                    JobEventService.close(event.id)
                    db.session.commit()
                    
                    logger.info(f"Outbox {outbox_item.id} completed successfully")
                    return True
                    
                except Exception as api_error:
                    # API call failed - handle retry logic
                    outbox_item.retry_count += 1
                    outbox_item.error_message = str(api_error)
                    
                    if outbox_item.retry_count < outbox_item.max_retries:
                        # Calculate exponential backoff: 2^retry_count seconds (2, 4, 8, 16, 32)
                        delay_seconds = 2 ** outbox_item.retry_count
                        outbox_item.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
                        outbox_item.status = 'pending'  # Reset to pending for retry
                        
                        logger.warning(
                            f"Outbox {outbox_item.id} failed, will retry ({outbox_item.retry_count}/{outbox_item.max_retries}): {str(api_error)[:100]}"
                        )
                    else:
                        # Max retries exceeded - mark as failed
                        outbox_item.status = 'failed'
                        logger.error(
                            f"Outbox {outbox_item.id} failed after {outbox_item.max_retries} retries: {str(api_error)[:100]}",
                            exc_info=True
                        )
                    
                    db.session.commit()
                    return False
                    
            elif outbox_item.destination == 'trello' and outbox_item.action == 'update_fab_order':
                # Get card_id from job record
                card_id = job_record.trello_card_id
                if not card_id:
                    logger.warning(f"Outbox {outbox_item.id}: Job {event.job}-{event.release} has no trello_card_id")
                    outbox_item.status = 'failed'
                    outbox_item.error_message = "Job has no trello_card_id"
                    db.session.commit()
                    return False
                
                # Derive fab_order from event payload
                fab_order = event.payload.get('to')
                # Allow None to clear the field
                
                # Execute the Trello API call
                try:
                    from app.trello.api import update_card_custom_field_number
                    from app.config import Config as cfg
                    from app.trello.utils import sort_list_if_needed
                    import math
                    
                    if cfg.FAB_ORDER_FIELD_ID:
                        # Convert fab_order to int if it's not None
                        if fab_order is not None:
                            if isinstance(fab_order, float):
                                fab_order_int = math.ceil(fab_order)
                            else:
                                fab_order_int = int(fab_order)
                            
                            # Update custom field
                            success = update_card_custom_field_number(
                                card_id,
                                cfg.FAB_ORDER_FIELD_ID,
                                fab_order_int
                            )
                            
                            if success:
                                # Get list_id from job record to check if sorting is needed
                                list_id = job_record.trello_list_id
                                if list_id:
                                    # Sort the list if it's one of the target lists
                                    sort_list_if_needed(
                                        list_id,
                                        cfg.FAB_ORDER_FIELD_ID,
                                        None,  # No operation_id for outbox processing
                                        "list"
                                    )
                                
                                # Success! Mark outbox item as completed
                                outbox_item.status = 'completed'
                                outbox_item.completed_at = datetime.utcnow()
                                outbox_item.error_message = None
                                db.session.commit()
                                
                                # Close the associated event now that external API call succeeded
                                JobEventService.close(event.id)
                                db.session.commit()
                                
                                logger.info(f"Outbox {outbox_item.id} completed successfully (fab_order update)")
                                return True
                            else:
                                raise Exception("Failed to update Trello custom field")
                        else:
                            # fab_order is None - we could clear the field, but for now just mark as success
                            # (Trello API doesn't have a clear way to remove custom field values)
                            outbox_item.status = 'completed'
                            outbox_item.completed_at = datetime.utcnow()
                            outbox_item.error_message = None
                            db.session.commit()
                            
                            JobEventService.close(event.id)
                            db.session.commit()
                            
                            logger.info(f"Outbox {outbox_item.id} completed (fab_order cleared)")
                            return True
                    else:
                        raise Exception("FAB_ORDER_FIELD_ID not configured")
                    
                except Exception as api_error:
                    # API call failed - handle retry logic
                    outbox_item.retry_count += 1
                    outbox_item.error_message = str(api_error)
                    
                    if outbox_item.retry_count < outbox_item.max_retries:
                        delay_seconds = 2 ** outbox_item.retry_count
                        outbox_item.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
                        outbox_item.status = 'pending'
                        
                        logger.warning(
                            f"Outbox {outbox_item.id} failed, will retry ({outbox_item.retry_count}/{outbox_item.max_retries}): {str(api_error)[:100]}"
                        )
                    else:
                        outbox_item.status = 'failed'
                        logger.error(
                            f"Outbox {outbox_item.id} failed after {outbox_item.max_retries} retries: {str(api_error)[:100]}",
                            exc_info=True
                        )
                    
                    db.session.commit()
                    return False
                    
            elif outbox_item.destination == 'trello' and outbox_item.action == 'update_notes':
                # Get card_id from job record
                card_id = job_record.trello_card_id
                if not card_id:
                    logger.warning(f"Outbox {outbox_item.id}: Job {event.job}-{event.release} has no trello_card_id")
                    outbox_item.status = 'failed'
                    outbox_item.error_message = "Job has no trello_card_id"
                    db.session.commit()
                    return False
                
                # Derive notes from event payload
                notes = event.payload.get('to', '')
                if not notes:
                    # Empty notes - nothing to do in Trello (comments can't be deleted via API easily)
                    outbox_item.status = 'completed'
                    outbox_item.completed_at = datetime.utcnow()
                    outbox_item.error_message = None
                    db.session.commit()
                    
                    JobEventService.close(event.id)
                    db.session.commit()
                    
                    logger.info(f"Outbox {outbox_item.id} completed (notes empty, skipping Trello)")
                    return True
                
                # Execute the Trello API call
                try:
                    from app.trello.api import add_comment_to_trello_card
                    
                    # Add comment to Trello card
                    success = add_comment_to_trello_card(card_id, str(notes))
                    
                    if success:
                        # Success! Mark outbox item as completed
                        outbox_item.status = 'completed'
                        outbox_item.completed_at = datetime.utcnow()
                        outbox_item.error_message = None
                        db.session.commit()
                        
                        # Close the associated event now that external API call succeeded
                        JobEventService.close(event.id)
                        db.session.commit()
                        
                        logger.info(f"Outbox {outbox_item.id} completed successfully (notes update)")
                        return True
                    else:
                        raise Exception("Failed to add comment to Trello card")
                    
                except Exception as api_error:
                    # API call failed - handle retry logic
                    outbox_item.retry_count += 1
                    outbox_item.error_message = str(api_error)
                    
                    if outbox_item.retry_count < outbox_item.max_retries:
                        delay_seconds = 2 ** outbox_item.retry_count
                        outbox_item.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
                        outbox_item.status = 'pending'
                        
                        logger.warning(
                            f"Outbox {outbox_item.id} failed, will retry ({outbox_item.retry_count}/{outbox_item.max_retries}): {str(api_error)[:100]}"
                        )
                    else:
                        outbox_item.status = 'failed'
                        logger.error(
                            f"Outbox {outbox_item.id} failed after {outbox_item.max_retries} retries: {str(api_error)[:100]}",
                            exc_info=True
                        )
                    
                    db.session.commit()
                    return False
            else:
                # Unsupported destination/action combination
                logger.error(f"Outbox {outbox_item.id}: Unsupported {outbox_item.destination}/{outbox_item.action}")
                outbox_item.status = 'failed'
                outbox_item.error_message = f"Unsupported: {outbox_item.destination}/{outbox_item.action}"
                db.session.commit()
                return False
                
        except Exception as e:
            # Unexpected error during processing
            logger.error(f"Outbox {outbox_item.id}: Unexpected error: {e}", exc_info=True)
            outbox_item.status = 'pending'  # Reset to pending so it can be retried
            outbox_item.error_message = f"Unexpected error: {str(e)}"
            outbox_item.retry_count += 1
            if outbox_item.retry_count < outbox_item.max_retries:
                delay_seconds = 2 ** outbox_item.retry_count
                outbox_item.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
            else:
                outbox_item.status = 'failed'
            db.session.commit()
            return False
    
    @staticmethod
    def process_pending_items(limit=10):
        """
        Process pending outbox items that are ready for retry.
        
        This method queries for items that are:
        - Status is 'pending'
        - next_retry_at is in the past (or now)
        
        Args:
            limit: Maximum number of items to process in this batch
            
        Returns:
            int: Number of items processed
        """
        from app.models import Outbox, db
        
        # Query for pending items ready to process
        now = datetime.utcnow()
        pending_items = Outbox.query.filter(
            Outbox.status == 'pending',
            Outbox.next_retry_at <= now
        ).limit(limit).all()
        
        if not pending_items:
            return 0
        
        processed_count = 0
        for item in pending_items:
            try:
                if OutboxService.process_item(item):
                    processed_count += 1
            except Exception as e:
                logger.error(f"Error processing outbox {item.id}: {e}", exc_info=True)
        
        if processed_count > 0:
            logger.debug(f"Processed {processed_count}/{len(pending_items)} outbox items")
        return processed_count