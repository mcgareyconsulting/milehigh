# app/brain/job_log/features/fab_order/events/outbox.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict


@dataclass
class OutboxItem:
    id: Optional[int]                 # Assigned by DB
    event_id: int                     # Foreign key to JobEvent
    destination: str                  # 'trello', 'procore', etc.
    action: str                       # 'move_card', 'update_fab_order', 'update_notes', etc.
    payload: Optional[Dict[str, Any]] # Optional extra data for processing
    status: str                       # 'pending', 'processing', 'completed', 'failed'
    retry_count: int
    max_retries: int
    next_retry_at: datetime
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
