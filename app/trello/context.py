"""
Context manager for sync operations.

This module provides a context manager that handles the lifecycle of sync operations:
- Creates operation records
- Tracks status transitions
- Handles errors and rollbacks
- Calculates duration
- Logs all events automatically
"""

from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

from app.models import SyncOperation, SyncStatus, db
from app.logging_config import get_logger
from app.trello.operations import create_sync_operation, update_sync_operation
from app.trello.logging import safe_log_sync_event

logger = get_logger(__name__)


@contextmanager
def sync_operation_context(
    operation_type: str,
    source_system: str,
    source_id: Optional[str] = None,
    require_db: bool = False
) -> Generator[Optional[SyncOperation], None, None]:
    """
    Context manager for sync operations that automatically handles:
    - Operation record creation
    - Status transitions (PENDING → IN_PROGRESS → COMPLETED/FAILED)
    - Error handling and database rollback
    - Duration calculation
    - Event logging
    
    Args:
        operation_type: Type of sync (e.g., 'trello_webhook') - onedrive_poll removed
        source_system: Source system name ('trello', 'system') - onedrive removed
        source_id: Identifier in source system (e.g., card_id)
        require_db: If True, raise exception if database unavailable
    
    Yields:
        SyncOperation instance, or None if database unavailable
    
    Example:
        >>> with sync_operation_context("trello_webhook", "trello", "card123") as sync_op:
        ...     # Do sync work here
        ...     card_data = get_trello_card_by_id("card123")
        ...     rec = Job.query.filter_by(...).first()
        ...     rec.trello_card_name = card_data["name"]
        ...     db.session.commit()
        ...     # Context manager handles success/failure automatically
    
    If an exception occurs:
        - Database changes are rolled back
        - Operation is marked as FAILED
        - Error is logged
        - Exception is re-raised
    
    If no exception:
        - Operation is marked as COMPLETED
        - Duration is calculated
        - Success is logged
    """
    sync_op = None
    start_time = datetime.utcnow()
    
    try:
        # Try to create sync operation
        sync_op = create_sync_operation(
            operation_type=operation_type,
            source_system=source_system,
            source_id=source_id
        )
        
        if sync_op is None:
            if require_db:
                raise RuntimeError("Database unavailable and required for sync operation")
            else:
                logger.warning(
                    "Database unavailable - proceeding without operation tracking",
                    operation_type=operation_type,
                    source_system=source_system
                )
                yield None
                return
        
        # Log creation
        safe_log_sync_event(
            sync_op.operation_id,
            "INFO",
            f"SyncOperation created: {operation_type}",
            source_system=source_system,
            source_id=source_id
        )
        
        # Update to in-progress
        update_sync_operation(
            sync_op.operation_id,
            status=SyncStatus.IN_PROGRESS
        )
        
        # Yield control to the with block
        yield sync_op
        
        # Success path - no exception was raised
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        update_sync_operation(
            sync_op.operation_id,
            status=SyncStatus.COMPLETED,
            completed_at=datetime.utcnow(),
            duration_seconds=duration
        )
        
        safe_log_sync_event(
            sync_op.operation_id,
            "INFO",
            f"SyncOperation completed successfully in {duration:.2f}s"
        )
        
    except Exception as e:
        # Error path - exception was raised
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        if sync_op:
            # Log the error
            safe_log_sync_event(
                sync_op.operation_id,
                "ERROR",
                f"SyncOperation failed: {type(e).__name__}",
                error=str(e),
                error_type=type(e).__name__
            )
            
            # Update to failed status
            update_sync_operation(
                sync_op.operation_id,
                status=SyncStatus.FAILED,
                error_type=type(e).__name__,
                error_message=str(e),
                completed_at=datetime.utcnow(),
                duration_seconds=duration
            )
        
        # Rollback any pending database changes
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.warning(
                "Failed to rollback database changes",
                error=str(rollback_error),
                operation_id=sync_op.operation_id if sync_op else None
            )
        
        # Re-raise the exception
        raise

