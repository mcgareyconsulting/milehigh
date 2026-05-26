"""
@milehigh-header
schema_version: 1
purpose: Record a vendor part pick-up against a release (DB row + audit event + Trello card outbox) as one command.
exports:
  RecordPickupCommand: Dataclass command that persists a PickupOrder and queues its Trello card.
  PickupResult: Re-exported result dataclass.
imports_from: [app.models, app.services.outbox_service, app.services.job_event_service]
imported_by: [app/pickup_email/ingest, app/brain/job_log/routes (future manual trigger)]
invariants:
  - Idempotent on email_message_id: a repeat of the same forwarded email is a no-op.
  - The matched release must already exist; a missing release raises ValueError.
  - Trello card creation is deferred to the outbox (action 'create_pickup_card') so it
    retries with backoff; the pickup_order_id is carried in the event payload so the
    outbox worker can write the resulting card id back onto the PickupOrder row.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Releases, PickupOrder, db
from app.services.outbox_service import OutboxService
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

from .results import PickupResult

logger = get_logger(__name__)


@dataclass
class RecordPickupCommand:
    """Record a forwarded vendor pick-up email against an existing release."""
    job_id: int
    release: str
    vendor: str = "Dencol"
    email_message_id: Optional[str] = None
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[str] = None
    email_body: Optional[str] = None
    email_received_at: Optional[datetime] = None
    source: str = "Email"

    def execute(self) -> PickupResult:
        release_rec: Releases = Releases.query.filter_by(
            job=self.job_id, release=self.release
        ).first()
        if not release_rec:
            logger.warning(f"Pickup: release not found {self.job_id}-{self.release}")
            raise ValueError(f"Release {self.job_id}-{self.release} not found")

        # Idempotency: the same forwarded email (Gmail message id) is a no-op.
        if self.email_message_id:
            existing = PickupOrder.query.filter_by(
                email_message_id=self.email_message_id
            ).first()
            if existing:
                logger.info(
                    f"Pickup already recorded for message {self.email_message_id} "
                    f"(pickup_order {existing.id})"
                )
                return PickupResult(
                    job_id=self.job_id,
                    release=self.release,
                    pickup_order_id=existing.id,
                    deduplicated=True,
                )

        pickup = PickupOrder(
            release_id=release_rec.id,
            job=self.job_id,
            release=self.release,
            vendor=self.vendor,
            email_message_id=self.email_message_id,
            email_subject=self.email_subject,
            email_from=self.email_from,
            email_to=self.email_to,
            email_received_at=self.email_received_at,
            email_body=self.email_body,
            status="received",
        )
        db.session.add(pickup)
        db.session.flush()  # assign pickup.id for the event payload + outbox link

        event_payload = {
            "pickup_order_id": pickup.id,
            "vendor": self.vendor,
            "subject": self.email_subject,
            "from": self.email_from,
            "to": self.email_to,
            "received_at": self.email_received_at.isoformat() if self.email_received_at else None,
            "body": self.email_body,
        }
        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action="pickup_received",
            source=self.source,
            payload=event_payload,
            external_user_id=self.email_from,
        )

        event_id = None
        if event is None:
            # Payload carries the unique pickup_order_id, so a dedup collision is
            # not expected. If it happens, keep the pickup row but skip the Trello
            # outbox (no event to anchor it to) and log for follow-up.
            logger.warning(
                f"Pickup event deduplicated for {self.job_id}-{self.release}; "
                f"Trello card not queued (pickup_order {pickup.id})"
            )
        else:
            event_id = event.id
            try:
                OutboxService.add(
                    destination="trello",
                    action="create_pickup_card",
                    event_id=event.id,
                )
            except Exception as outbox_error:
                logger.error(
                    f"Failed to queue pickup card outbox for event {event.id}: {outbox_error}",
                    exc_info=True,
                )

        db.session.commit()

        logger.info(
            "pickup recorded",
            extra={
                "job": self.job_id,
                "release": self.release,
                "pickup_order_id": pickup.id,
                "event_id": event_id,
            },
        )

        return PickupResult(
            job_id=self.job_id,
            release=self.release,
            pickup_order_id=pickup.id,
            event_id=event_id,
        )
