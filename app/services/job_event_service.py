from datetime import datetime
from app.logging_config import get_logger
from app.auth.utils import format_source_with_user, get_current_user

logger = get_logger(__name__)

class JobEventService:
    """Service for managing job events"""
    
    @staticmethod
    def create(job, release, action, source, payload):
        """
        Create a new job event with deduplication.
        
        Args:
            job: Job number
            release: Release string
            action: Action string
            source: Base source string (e.g., 'Brain', 'Procore')
            payload: Event payload dict
        
        Returns:
            JobEvents object if created
            None if duplicate detected
        """
        from app.models import JobEvents, db
        import json
        import hashlib
        
        # Get current user and format source with username
        # Only get user for Brain-specific updates (external sources like Trello handle their own formatting)
        if " - " in source:
            # Source is already formatted (e.g., "Trello - username"), use as-is
            user = None
            formatted_source = source
        elif source == "Brain":
            # Brain updates: get user from session and format
            user = get_current_user()
            formatted_source = format_source_with_user(source, user)
        else:
            # External sources (Trello, Procore, etc.) - don't get user, use source as-is
            user = None
            formatted_source = source
        
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
            'source': formatted_source
        })
        
        event = JobEvents(
            job=job,
            release=release,
            action=action,
            payload=payload,
            payload_hash=payload_hash,
            source=formatted_source,
            user_id=user.id if user else None,
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

