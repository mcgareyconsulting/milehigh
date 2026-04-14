"""
@milehigh-header
schema_version: 1
purpose: Define the structured result type returned by fab_order update operations for consistent API responses.
exports:
  FabOrderUpdateResult: Dataclass holding job_id, release, event_id, fab_order, and status with JSON serialization
imports_from: [dataclasses, typing]
imported_by: [app/brain/job_log/features/fab_order/command.py]
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class FabOrderUpdateResult:
    job_id: int
    release: str
    event_id: int
    fab_order: Optional[float]
    status: str = "success"

    def to_dict(self) -> dict:
        """Serialize for JSON response"""
        return {
            "job_id": self.job_id,
            "release": self.release,
            "event_id": self.event_id,
            "fab_order": self.fab_order,
            "status": self.status
        }
