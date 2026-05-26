"""
@milehigh-header
schema_version: 1
purpose: Result object returned by RecordPickupCommand.
exports:
  PickupResult: Dataclass with pickup_order_id, event_id, and whether it was a no-op.
imports_from: [dataclasses, typing]
imported_by: [app/brain/job_log/features/pickup/command, app/pickup_email/ingest]
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PickupResult:
    job_id: int
    release: str
    pickup_order_id: int
    event_id: Optional[int] = None
    # True when an existing PickupOrder for the same email_message_id was found
    # and nothing new was created (idempotent replay of the same forwarded email).
    deduplicated: bool = False
    status: str = "success"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "release": self.release,
            "pickup_order_id": self.pickup_order_id,
            "event_id": self.event_id,
            "deduplicated": self.deduplicated,
            "status": self.status,
        }
