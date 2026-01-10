"""
Logging utilities for sync operations.

This module provides safe logging that handles JSON serialization issues
and integrates with the SyncLog database model.
"""

import time
from typing import Any, Optional
from datetime import datetime, date
from decimal import Decimal

import numpy as np
import pandas as pd

from app.models import SyncLog, db
from app.logging_config import get_logger


logger = get_logger(__name__)


def make_json_safe(obj: Any) -> Any:
    """
    Convert problematic types to JSON-serializable types.
    
    Args:
        obj: Any Python object
    
    Returns:
        JSON-serializable version of the object
    
    Handles:
        - Pandas NA, Timestamp, Series, DataFrame
        - NumPy integers, floats, booleans, arrays
        - Python datetime, date objects
        - Decimal numbers
        - Nested dicts, lists, tuples, sets
    """
    # Handle pandas NA
    if obj is pd.NA:
        return None
    
    # Handle NumPy types
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    
    # Handle pandas types
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    
    # Handle datetime types
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    
    # Handle Decimal
    elif isinstance(obj, Decimal):
        return float(obj)
    
    # Handle other numpy scalars
    elif hasattr(obj, 'item'):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    
    # Handle collections recursively
    elif isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, set):
        return [make_json_safe(item) for item in obj]
    
    # Return as-is for already JSON-safe types
    else:
        return obj


def safe_log_sync_event(
    operation_id: str,
    level: str,
    message: str,
    **kwargs
) -> bool:
    """
    Safely log a sync event to the database.
    
    This function handles JSON serialization issues and retries on failure.
    It will not raise exceptions - failures are logged to the standard logger.
    
    Args:
        operation_id: ID of the sync operation
        level: Log level (INFO, WARNING, ERROR, etc.)
        message: Log message
        **kwargs: Additional data to log (will be JSON-serialized)
    
    Returns:
        True if logging succeeded, False otherwise
    
    Example:
        >>> safe_log_sync_event(
        ...     "abc123",
        ...     "INFO",
        ...     "Processing record",
        ...     job_id=42,
        ...     trello_card_id="xyz789",
        ...     status="active"
        ... )
        True
    """
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Extract well-known identifiers for first-class columns
            job_id = kwargs.pop("job_id", None)
            trello_card_id = kwargs.pop("trello_card_id", None) or kwargs.pop("card_id", None)
            excel_identifier = kwargs.pop("excel_identifier", None)
            
            # Convert data to JSON-safe format
            safe_data = make_json_safe(kwargs)
            
            # Create log entry
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
            
            return True  # Success
            
        except Exception as e:
            # Rollback on failure
            try:
                db.session.rollback()
            except Exception:
                pass
            
            if attempt < max_retries - 1:
                # Exponential backoff before retry
                time.sleep(0.1 * (2 ** attempt))
                continue
            else:
                # Final attempt failed - log to standard logger
                logger.warning(
                    "Failed to log sync event after retries",
                    error=str(e),
                    error_type=type(e).__name__,
                    operation_id=operation_id,
                    message=message,
                    attempt=attempt + 1
                )
                return False
    
    return False


def safe_sync_op_call(sync_op: Optional[Any], func: callable, *args, **kwargs) -> Any:
    """
    Safely call a function with sync operation context.
    
    This wrapper ensures that even if sync_op is None (e.g., database unavailable),
    the function can still be called without errors.
    
    Args:
        sync_op: SyncOperation instance or None
        func: Function to call
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
    
    Returns:
        Result of the function call, or None if sync_op is None or call fails
    
    Example:
        >>> sync_op = create_sync_operation(...)
        >>> safe_sync_op_call(
        ...     sync_op,
        ...     safe_log_sync_event,
        ...     "INFO",
        ...     "Processing started"
        ... )
    """
    if sync_op is None:
        return None
    
    try:
        # If function expects operation_id as first arg, pass it
        if func.__name__ in ('safe_log_sync_event', 'update_sync_operation'):
            return func(sync_op.operation_id, *args, **kwargs)
        else:
            return func(*args, **kwargs)
            
    except Exception as e:
        logger.warning(
            "Failed to execute sync operation call",
            error=str(e),
            error_type=type(e).__name__,
            operation_id=getattr(sync_op, 'operation_id', None),
            function_name=func.__name__ if hasattr(func, '__name__') else str(func)
        )
        return None

