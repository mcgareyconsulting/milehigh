from datetime import datetime
from app.logging_config import get_logger
from app.auth.utils import get_current_user

logger = get_logger(__name__)

class JobEventService:
    """Service for managing job events"""
    
    @staticmethod
    def create(job, release, action, source, payload, external_user_id=None):
        """
        Create a new job event with deduplication.
        
        Args:
            job: Job number
            release: Release string
            action: Action string
            source: Base source string (e.g., 'Brain', 'Trello', 'Excel', 'Procore')
            payload: Event payload dict
            external_user_id: Optional external user id (e.g. Trello member id, Procore user id)
        
        Returns:
            JobEvents object if created
            None if duplicate detected
        """
        from app.models import ReleaseEvents, db
        import json
        import hashlib
        
        # Resolve internal_user_id: Brain uses get_current_user(); Trello resolves via users.trello_id
        internal_user_id = None
        if source == "Brain":
            user = get_current_user()
            internal_user_id = user.id if user else None
        elif source == "Trello" and external_user_id:
            from app.trello.helpers import resolve_internal_user_id_from_trello
            internal_user_id = resolve_internal_user_id_from_trello(external_user_id)
        
        # Generate payload hash for deduplication
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        hash_string = f"{action}:{job}:{release}:{payload_json}"
        payload_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
        
        # Check for duplicate
        existing = ReleaseEvents.query.filter_by(payload_hash=payload_hash).first()
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
            'source': source,
            'external_user_id': external_user_id,
            'internal_user_id': internal_user_id,
        })
        
        event = ReleaseEvents(
            job=job,
            release=release,
            action=action,
            payload=payload,
            payload_hash=payload_hash,
            source=source,
            internal_user_id=internal_user_id,
            external_user_id=external_user_id,
            created_at=datetime.utcnow()
        )
        
        db.session.add(event)
        db.session.flush()  # Get the ID without committing
        
        logger.info(f"Job event created: {event.id}")
        return event
    
    @staticmethod
    def close(event_id):
        """Mark event as applied"""
        from app.models import ReleaseEvents, db
        
        event = ReleaseEvents.query.get(event_id)
        if event:
            event.applied_at = datetime.utcnow()
            logger.debug(f"Event {event_id} marked as applied")
        else:
            logger.warning(f"Attempted to close non-existent event {event_id}")

