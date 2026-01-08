from datetime import datetime
from app.logging_config import get_logger
logger = get_logger(__name__)

class OutboxService:
    """Service for managing outbox items"""
    
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
        
        logger.info(f"Adding to outbox", extra={
            'destination': destination,
            'action': action,
            'event_id': event_id
        })
        
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
        
        logger.info(f"Outbox item created: {outbox_item.id}")
        return outbox_item