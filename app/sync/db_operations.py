"""
Database operations for SyncOperation records.

This module handles all CRUD operations for SyncOperation records,
providing a clean interface for tracking sync operations.
"""

from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy.exc import SQLAlchemyError

from app.models import SyncOperation, SyncStatus, db
from app.logging_config import get_logger

logger = get_logger(__name__)

def create_sync_operation(operation_type: str, source_system: str = None, source_id: str = None) -> SyncOperation:
    """Create a new sync operation record."""
    operation_id = str(uuid.uuid4())[:8]
    sync_op = SyncOperation(
        operation_id=operation_id,
        operation_type=operation_type,
        status=SyncStatus.PENDING,
        source_system=source_system,
        source_id=source_id
    )
    db.session.add(sync_op)
    db.session.commit()
    return sync_op

def update_sync_operation(operation_id: str, **kwargs):
    """Update a sync operation record with proper error handling."""
    try:
        sync_op = SyncOperation.query.filter_by(operation_id=operation_id).first()
        if sync_op:
            for key, value in kwargs.items():
                if hasattr(sync_op, key):
                    setattr(sync_op, key, value)
            db.session.commit()
        return sync_op
    except Exception as e:
        # Log the error but don't let it break the sync
        logger.warning(
            "Failed to update sync operation", 
            operation_id=operation_id, 
            error=str(e),
            error_type=type(e).__name__
        )
        try:
            db.session.rollback()
        except Exception:
            pass  # Ignore rollback errors
        return None