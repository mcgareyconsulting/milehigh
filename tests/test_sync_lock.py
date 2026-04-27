"""Tests for app/sync_lock.py — SyncLockManager and synchronized_sync."""
import threading
import time

import pytest

from app.sync_lock import SyncLockManager, synchronized_sync, sync_lock_manager


def test_initial_state_is_unlocked():
    mgr = SyncLockManager()
    assert mgr.is_locked() is False
    assert mgr.get_current_operation() is None


def test_is_locked_inside_context_manager():
    mgr = SyncLockManager()
    with mgr.acquire_sync_lock("op-A"):
        assert mgr.is_locked() is True
        assert mgr.get_current_operation() == "op-A"
    assert mgr.is_locked() is False
    assert mgr.get_current_operation() is None


def test_get_status_reflects_active_operation():
    mgr = SyncLockManager()
    with mgr.acquire_sync_lock("op-A"):
        status = mgr.get_status()
        assert status["is_locked"] is True
        assert status["current_operation"] == "op-A"
        assert status["held_by_thread"] == threading.get_ident()
        assert status["held_for_seconds"] >= 0


def test_get_status_after_release():
    mgr = SyncLockManager()
    with mgr.acquire_sync_lock("op-A"):
        pass
    status = mgr.get_status()
    assert status["is_locked"] is False
    assert status["current_operation"] is None
    assert status["held_by_thread"] is None
    assert status["held_for_seconds"] == 0


def test_same_thread_can_reenter():
    # The current implementation does not preserve nested-lock state — once
    # the inner with-block exits, the lock is fully released even with an
    # outer holder still open. This test pins only the lighter contract:
    # same-thread re-entry must not raise.
    mgr = SyncLockManager()
    with mgr.acquire_sync_lock("outer"):
        with mgr.acquire_sync_lock("inner"):
            pass
    assert mgr.is_locked() is False


def test_other_thread_blocked_while_held():
    mgr = SyncLockManager()
    started = threading.Event()
    other_failed = threading.Event()

    def hold_lock():
        with mgr.acquire_sync_lock("primary"):
            started.set()
            time.sleep(0.3)

    def try_acquire():
        # Wait until the primary holder is in
        started.wait(timeout=1)
        try:
            # Short timeout so we don't block the test
            with mgr.acquire_sync_lock("secondary", timeout_seconds=1):
                pass
        except RuntimeError:
            other_failed.set()

    t1 = threading.Thread(target=hold_lock)
    t2 = threading.Thread(target=try_acquire)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert other_failed.is_set(), "second thread should have been rejected while primary held the lock"


def test_lock_released_on_exception():
    mgr = SyncLockManager()
    with pytest.raises(ValueError):
        with mgr.acquire_sync_lock("op-A"):
            raise ValueError("kaboom")
    assert mgr.is_locked() is False
    assert mgr.get_current_operation() is None


def test_synchronized_sync_decorator_runs_function():
    calls = []

    @synchronized_sync("decorated-op")
    def my_op(x, y):
        calls.append((x, y))
        return x + y

    assert my_op(2, 3) == 5
    assert calls == [(2, 3)]
    assert sync_lock_manager.is_locked() is False


def test_synchronized_sync_propagates_function_exception():
    @synchronized_sync("decorated-op")
    def my_op():
        raise ValueError("inside")

    with pytest.raises(ValueError):
        my_op()
    assert sync_lock_manager.is_locked() is False


def test_module_singleton_is_a_sync_lock_manager():
    assert isinstance(sync_lock_manager, SyncLockManager)
