from datetime import datetime
from app.logging_config import get_logger
logger = get_logger(__name__)

class JobEventService:
    """Service for managing job events"""
    
    @staticmethod
    def create(job, release, action, source, payload):
        """
        Create a new job event with deduplication.
        
        Returns:
            JobEvents object if created
            None if duplicate detected
        """
        from app.models import JobEvents, db
        import json
        import hashlib
        
        # Generate payload hash for deduplication
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        hash_string = f"{action}:{job}:{release}:{payload_json}"
        payload_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
        
        # Check for duplicate
        existing = JobEvents.query.filter_by(payload_hash=payload_hash).first()
        if existing:
            logger.info(f"Duplicate event detected", extra={
                'job': job,
                'release': release,
                'action': action,
                'existing_event_id': existing.id
            })
            return None
        
        # Create event
        logger.info(f"Creating job event", extra={
            'job': job,
            'release': release,
            'action': action,
            'source': source
        })
        
        event = JobEvents(
            job=job,
            release=release,
            action=action,
            payload=payload,
            payload_hash=payload_hash,
            source=source,
            created_at=datetime.utcnow()
        )
        
        db.session.add(event)
        db.session.flush()  # Get the ID without committing
        
        logger.info(f"Job event created: {event.id}")
        return event
    
    @staticmethod
    def close(event_id):
        """Mark event as applied"""
        from app.models import JobEvents, db
        
        event = JobEvents.query.get(event_id)
        if event:
            event.applied_at = datetime.utcnow()
            logger.debug(f"Event {event_id} marked as applied")
        else:
            logger.warning(f"Attempted to close non-existent event {event_id}")

