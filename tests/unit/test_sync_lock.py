"""
Unit tests for sync lock manager.
"""
import pytest
import threading
import time
from unittest.mock import patch
from datetime import datetime
from app.sync_lock import SyncLockManager, synchronized_sync


@pytest.mark.unit
@pytest.mark.sync
class TestSyncLockManager:
    """Test the SyncLockManager class."""
    
    def test_initial_state(self):
        """Test initial state of lock manager."""
        manager = SyncLockManager()
        
        assert not manager.is_locked()
        assert manager.get_current_operation() is None
        
        status = manager.get_status()
        assert not status["is_locked"]
        assert status["current_operation"] is None
        assert status["held_by_thread"] is None
        assert status["held_for_seconds"] == 0
    
    def test_acquire_and_release_lock(self):
        """Test basic lock acquisition and release."""
        manager = SyncLockManager()
        
        with manager.acquire_sync_lock("test_operation"):
            assert manager.is_locked()
            assert manager.get_current_operation() == "test_operation"
        
        assert not manager.is_locked()
        assert manager.get_current_operation() is None
    
    def test_lock_prevents_concurrent_access(self):
        """Test that lock prevents concurrent access."""
        manager = SyncLockManager()
        results = []
        
        def first_operation():
            with manager.acquire_sync_lock("first_op"):
                results.append("first_started")
                time.sleep(0.1)  # Hold the lock briefly
                results.append("first_completed")
        
        def second_operation():
            try:
                with manager.acquire_sync_lock("second_op", timeout_seconds=0.05):
                    results.append("second_started")
            except RuntimeError as e:
                results.append(f"second_failed: {str(e)}")
        
        # Start first operation in a thread
        thread1 = threading.Thread(target=first_operation)
        thread1.start()
        
        # Give first operation time to acquire lock
        time.sleep(0.02)
        
        # Try second operation - should fail
        thread2 = threading.Thread(target=second_operation)
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        assert "first_started" in results
        assert "first_completed" in results
        assert any("second_failed" in result for result in results)
        assert "second_started" not in results
    
    def test_reentrant_lock_same_thread(self):
        """Test that the same thread can re-acquire the lock."""
        manager = SyncLockManager()
        results = []
        
        def nested_operation():
            with manager.acquire_sync_lock("outer_op"):
                results.append("outer_acquired")
                with manager.acquire_sync_lock("inner_op"):
                    results.append("inner_acquired")
                    assert manager.get_current_operation() == "inner_op"
                results.append("inner_released")
            results.append("outer_released")
        
        nested_operation()
        
        assert results == [
            "outer_acquired",
            "inner_acquired", 
            "inner_released",
            "outer_released"
        ]
        assert not manager.is_locked()
    
    def test_lock_timeout(self):
        """Test lock acquisition timeout."""
        manager = SyncLockManager()
        
        def hold_lock():
            with manager.acquire_sync_lock("holding_op"):
                time.sleep(0.2)
        
        # Start thread that holds the lock
        thread = threading.Thread(target=hold_lock)
        thread.start()
        
        # Give it time to acquire lock
        time.sleep(0.05)
        
        # Try to acquire with short timeout - should fail
        start_time = time.time()
        with pytest.raises(RuntimeError, match="Lock acquisition timed out"):
            with manager.acquire_sync_lock("timeout_op", timeout_seconds=0.05):
                pass
        
        elapsed = time.time() - start_time
        assert elapsed >= 0.05  # Should have waited for timeout
        assert elapsed < 0.15   # But not much longer
        
        thread.join()
    
    def test_get_status_with_active_lock(self):
        """Test status reporting with active lock."""
        manager = SyncLockManager()
        
        with manager.acquire_sync_lock("status_test_op"):
            status = manager.get_status()
            
            assert status["is_locked"] is True
            assert status["current_operation"] == "status_test_op"
            assert status["held_by_thread"] == threading.get_ident()
            assert status["held_for_seconds"] >= 0
            assert status["timeout_seconds"] == 60
    
    def test_exception_in_locked_section(self):
        """Test that exceptions properly release the lock."""
        manager = SyncLockManager()
        
        with pytest.raises(ValueError, match="test error"):
            with manager.acquire_sync_lock("error_op"):
                assert manager.is_locked()
                raise ValueError("test error")
        
        # Lock should be released even after exception
        assert not manager.is_locked()
        assert manager.get_current_operation() is None


@pytest.mark.unit
@pytest.mark.sync
class TestSynchronizedSyncDecorator:
    """Test the synchronized_sync decorator."""
    
    def test_synchronized_sync_decorator(self):
        """Test basic functionality of synchronized_sync decorator."""
        results = []
        
        @synchronized_sync("decorated_op")
        def test_function():
            results.append("function_executed")
            return "success"
        
        result = test_function()
        
        assert result == "success"
        assert "function_executed" in results
    
    def test_synchronized_sync_prevents_concurrent_execution(self):
        """Test that decorator prevents concurrent execution."""
        results = []
        
        @synchronized_sync("concurrent_test")
        def slow_function():
            results.append("started")
            time.sleep(0.1)
            results.append("completed")
            return "done"
        
        def run_function():
            try:
                result = slow_function()
                results.append(f"result: {result}")
            except RuntimeError as e:
                results.append(f"error: {str(e)}")
        
        # Start two threads
        thread1 = threading.Thread(target=run_function)
        thread2 = threading.Thread(target=run_function)
        
        thread1.start()
        time.sleep(0.02)  # Let first thread start
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # First should succeed, second should fail
        assert "started" in results
        assert "completed" in results
        assert "result: done" in results
        assert any("error:" in result for result in results)
    
    def test_synchronized_sync_with_exception(self):
        """Test that decorator handles exceptions properly."""
        @synchronized_sync("exception_test")
        def failing_function():
            raise ValueError("test error")
        
        with pytest.raises(ValueError, match="test error"):
            failing_function()
    
    def test_synchronized_sync_with_arguments(self):
        """Test decorator with function arguments."""
        @synchronized_sync("args_test")
        def function_with_args(a, b, c=None):
            return f"a={a}, b={b}, c={c}"
        
        result = function_with_args("hello", "world", c="test")
        assert result == "a=hello, b=world, c=test"
    
    @patch('app.sync_lock.logger')
    def test_synchronized_sync_logs_lock_failure(self, mock_logger):
        """Test that decorator logs lock acquisition failures."""
        # Create a manager with a very short timeout for testing
        with patch('app.sync_lock.sync_lock_manager') as mock_manager:
            mock_manager.acquire_sync_lock.side_effect = RuntimeError("Lock busy")
            
            @synchronized_sync("log_test")
            def test_function():
                return "success"
            
            with pytest.raises(RuntimeError, match="Lock busy"):
                test_function()
            
            mock_logger.warning.assert_called_once()
            args = mock_logger.warning.call_args[0]
            assert "Cannot execute log_test" in args[0]
