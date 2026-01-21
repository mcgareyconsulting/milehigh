# app/brain/job_log/features/fab_order/events.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class JobEvent:
    id: Optional[int]           # Will be None until saved to DB
    job: int
    release: str
    action: str
    source: str
    payload: Dict[str, Any]
    payload_hash: str
    created_at: datetime
    applied_at: Optional[datetime] = None
