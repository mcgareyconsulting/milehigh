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
