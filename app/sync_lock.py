import threading
import logging
from contextlib import contextmanager
from typing import Optional
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncLockManager:
    """
    Simple sync lock manager to prevent concurrent sync operations
    Step 1: Basic locking only, no queue system yet
    """

    def __init__(self):
        self._lock = threading.RLock()  # Reentrant lock
        self._is_syncing = False
        self._current_operation = None

    def is_locked(self) -> bool:
        """Check if sync is currently locked"""
        with self._lock:
            return self._is_syncing

    def get_current_operation(self) -> Optional[str]:
        """Get the name of the current operation holding the lock"""
        with self._lock:
            return self._current_operation if self._is_syncing else None

    @contextmanager
    def acquire_sync_lock(self, operation_name: str):
        """
        Context manager to acquire sync lock

        Args:
            operation_name: Name of the operation acquiring the lock

        Raises:
            RuntimeError: If unable to acquire lock (another sync is running)
        """
        acquired = False
        try:
            with self._lock:
                if self._is_syncing:
                    current_op = self._current_operation
                    logger.warning(
                        f"Sync lock already held by '{current_op}'. "
                        f"Cannot acquire for '{operation_name}'"
                    )
                    raise RuntimeError(f"Sync already in progress: {current_op}")

                self._is_syncing = True
                self._current_operation = operation_name
                acquired = True
                logger.info(f"Sync lock acquired for operation: {operation_name}")

            yield  # This is where the sync operation runs

        finally:
            if acquired:
                with self._lock:
                    self._is_syncing = False
                    self._current_operation = None
                    logger.info(f"Sync lock released for operation: {operation_name}")

    def get_status(self) -> dict:
        """Get current status of the lock manager"""
        return {
            "is_locked": self.is_locked(),
            "current_operation": self.get_current_operation(),
            "timestamp": datetime.now().isoformat(),
        }


# Global instance - create once and reuse
sync_lock_manager = SyncLockManager()


# Decorator to make any function synchronized
def synchronized_sync(operation_name: str):
    """
    Decorator to ensure sync function runs with proper locking

    Args:
        operation_name: Name to identify the sync operation
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                with sync_lock_manager.acquire_sync_lock(operation_name):
                    return func(*args, **kwargs)
            except RuntimeError as e:
                logger.warning(f"Cannot execute {operation_name}: {e}")
                raise

        return wrapper

    return decorator
