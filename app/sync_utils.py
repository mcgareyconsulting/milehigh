"""
Utility functions for sync operations to avoid circular imports.
"""
import pandas as pd
from datetime import datetime, date
from typing import Optional, Any
from app.models import Job, SyncOperation, SyncStatus, SyncLog, db
from app.logging_config import get_logger
import uuid
import numpy as np

logger = get_logger(__name__)


def safe_log_sync_event(operation_id: str, level: str, message: str, **kwargs):
    """Safely log a sync event, converting problematic types."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Convert problematic types to safe JSON-serializable types
            def make_json_safe(obj):
                if obj is pd.NA:
                    return None
                if isinstance(obj, (np.integer, np.int64, np.int32)):
                    return int(obj)
                elif isinstance(obj, (np.floating, np.float64, np.float32)):
                    return float(obj)
                elif isinstance(obj, (np.bool_,)):
                    return bool(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, pd.Timestamp):
                    return obj.isoformat()
                elif isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: make_json_safe(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [make_json_safe(item) for item in obj]
                elif isinstance(obj, set):
                    return [make_json_safe(item) for item in obj]
                else:
                    return obj
            
            # Extract well-known identifiers for first-class columns
            job_id = kwargs.pop("job_id", None)
            trello_card_id = kwargs.pop("trello_card_id", None) or kwargs.pop("card_id", None)
            excel_identifier = kwargs.pop("excel_identifier", None)

            safe_data = make_json_safe(kwargs)
            
            sync_log = SyncLog(
                operation_id=operation_id,
                level=level,
                message=message,
                job_id=job_id,
                trello_card_id=trello_card_id,
                excel_identifier=excel_identifier,
                data=safe_data
            )
            db.session.add(sync_log)
            db.session.commit()
            return  # Success, exit retry loop
            
        except Exception as e:
            # Don't let logging failures break the sync
            try:
                db.session.rollback()
            except Exception:
                pass
            
            if attempt < max_retries - 1:
                # Wait before retry (exponential backoff)
                import time
                time.sleep(0.1 * (2 ** attempt))
                continue
            else:
                # Final attempt failed
                logger.warning("Failed to log sync event after retries", 
                             error=str(e), 
                             operation_id=operation_id, 
                             message=message,
                             error_type=type(e).__name__)
                break


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


def compare_timestamps(event_time, source_time, operation_id: str):
    """Compare external event timestamp with database record timestamp."""
    if not event_time:
        logger.warning("Invalid event_time (None)", operation_id=operation_id)
        return None

    if not source_time:
        logger.info("No DB timestamp — treating event as newer", operation_id=operation_id)
        return "newer"

    if event_time > source_time:
        logger.info("Event is newer than DB record", operation_id=operation_id)
        return "newer"
    else:
        logger.info("Event is older than DB record", operation_id=operation_id)
        return "older"


def check_database_connection():
    """Check if database connection is working."""
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("Database connection check failed", error=str(e))
        return False


def safe_sync_op_call(sync_op, func, *args, **kwargs):
    """Safely call a function with sync operation context."""
    if sync_op:
        try:
            return func(sync_op.operation_id, *args, **kwargs)
        except Exception as e:
            logger.warning("Failed to execute sync operation call", 
                         error=str(e), 
                         operation_id=sync_op.operation_id,
                         function_name=func.__name__ if hasattr(func, '__name__') else str(func))
    return None


def as_date(val):
    """Convert value to date."""
    if pd.isna(val) or val is None:
        return None
    # Handle pd.Timestamp, datetime, string, etc.
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    # Try parsing string
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None
