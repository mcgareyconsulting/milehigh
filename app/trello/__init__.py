"""
@milehigh-header
schema_version: 1
purpose: Drains the Trello webhook queue on a thread pool, holding the sync lock to serialize webhook handlers against the scheduled queue drainer.
exports:
  trello_bp: Flask blueprint for /trello routes (webhook receiver, thread stats)
  drain_trello_queue: Processes queued events when the sync lock is free (called by APScheduler every 5 min)
  trello_event_queue: Bounded in-memory queue (maxsize=1000) buffering events while lock is held
  ThreadTracker: Tracks thread pool utilization stats (started, completed, failed, rejected)
  thread_tracker: Module-level ThreadTracker singleton
imports_from: [app/trello/utils, app/trello/sync, app/sync_lock, flask, concurrent.futures]
imported_by: [app/__init__.py]
invariants:
  - Must hold sync_lock before calling sync_from_trello — webhook handler and queue drainer cannot run concurrently.
  - When lock is held, events are queued (HTTP 202) not dropped; queue full returns 429.
  - drain_trello_queue is a scheduler job — get_current_user() will return None; do not call it here.
  - executor is a 10-worker ThreadPoolExecutor; increasing workers risks sync lock contention.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
from flask import Blueprint, request, current_app, jsonify
from app.trello.utils import parse_webhook_data
from app.trello.sync import sync_from_trello
from app.sync_lock import sync_lock_manager
from app.logging_config import get_logger
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from queue import Queue, Full, Empty
import time

logger = get_logger(__name__)


class ThreadTracker:
    def __init__(self):
        self.stats = {
            "total_started": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_rejected": 0,  # Add rejected counter
            "active_count": 0,
            "max_concurrent": 0,
        }
        self.lock = threading.Lock()
        self.start_times = {}  # Track execution times

    def thread_started(self, thread_id):
        with self.lock:
            self.stats["total_started"] += 1
            self.stats["active_count"] += 1
            self.stats["max_concurrent"] = max(
                self.stats["max_concurrent"], self.stats["active_count"]
            )
            self.start_times[thread_id] = time.time()

    def thread_completed(self, thread_id, success=True):
        with self.lock:
            self.stats["active_count"] -= 1
            if success:
                self.stats["total_completed"] += 1
            else:
                self.stats["total_failed"] += 1

            # Calculate execution time
            if thread_id in self.start_times:
                duration = time.time() - self.start_times[thread_id]
                del self.start_times[thread_id]
                return duration
        return None

    def thread_rejected(self):
        with self.lock:
            self.stats["total_rejected"] += 1


# Global tracker and thread pool
thread_tracker = ThreadTracker()
executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="sync-")
# Bounded in-memory queue to buffer Trello events when lock is busy
trello_event_queue: Queue = Queue(maxsize=1000)

# Blueprint for Trello routes
trello_bp = Blueprint("trello", __name__)


@trello_bp.route("/webhook", methods=["HEAD", "POST"])
def trello_webhook():
    if request.method == "HEAD":
        return "", 200

    if request.method == "POST":
        if current_app.config.get("TRELLO_MOCK"):
            logger.info("trello_mock_webhook_dropped", source="trello")
            return "", 200

        data = request.json
        event_info = parse_webhook_data(data)
        app = current_app._get_current_object()

        # Skip unhandled webhooks
        if not event_info.get("handled"):
            action_type = event_info.get("action_type", "unknown")
            logger.debug("trello_webhook_skipped", action_type=action_type, source="trello")
            return "", 200

        # If locked, enqueue the event for later processing and return 202
        if sync_lock_manager.is_locked():
            current_op = sync_lock_manager.get_current_operation()
            try:
                trello_event_queue.put_nowait(event_info)
                thread_tracker.thread_rejected()
                logger.info(
                    "trello_webhook_queued",
                    lock_holder=current_op,
                    card_id=event_info.get("card_id"),
                    source="trello",
                    status="queued",
                )
                return jsonify({"status": "queued", "reason": f"lock_held_by_{current_op}"}), 202
            except Full:
                thread_tracker.thread_rejected()
                logger.warning(
                    "trello_queue_full",
                    card_id=event_info.get("card_id"),
                    source="trello",
                    status="skipped",
                )
                return jsonify({"status": "overloaded"}), 429

        def run_sync():
            thread_id = threading.current_thread().ident
            thread_tracker.thread_started(thread_id)

            try:
                with app.app_context():
                    # Double-check lock status before attempting acquisition
                    # This handles race conditions where another operation started
                    # between the initial check and thread execution
                    if sync_lock_manager.is_locked():
                        current_op = sync_lock_manager.get_current_operation()
                        logger.info(
                            "trello_webhook_requeued",
                            lock_holder=current_op,
                            card_id=event_info.get("card_id"),
                            source="trello",
                            status="queued",
                        )
                        try:
                            trello_event_queue.put_nowait(event_info)
                        except Full:
                            logger.warning(
                                "trello_event_requeue_failed",
                                reason="queue_full",
                                card_id=event_info.get("card_id"),
                                source="trello",
                            )
                        duration = thread_tracker.thread_completed(thread_id, success=False)
                        thread_tracker.thread_rejected()
                        return

                    # Try to acquire the sync lock in the thread
                    try:
                        with sync_lock_manager.acquire_sync_lock("Trello-Hook"):
                            logger.debug("trello_sync_started", card_id=event_info.get("card_id"), source="trello")
                            sync_from_trello(event_info)
                            logger.debug("trello_sync_finished", card_id=event_info.get("card_id"), source="trello")

                        duration = thread_tracker.thread_completed(
                            thread_id, success=True
                        )
                        logger.info(
                            "trello_sync_completed",
                            duration_ms=int(duration * 1000),
                            card_id=event_info.get("card_id"),
                            source="trello",
                            status="ok",
                        )

                    except RuntimeError as lock_error:
                        # Lock acquisition failed - this shouldn't happen since we checked above
                        # but it's possible another sync started between the check and thread execution
                        logger.warning(
                            "trello_sync_lock_failed",
                            error=str(lock_error),
                            error_type=type(lock_error).__name__,
                            card_id=event_info.get("card_id"),
                            source="trello",
                        )
                        duration = thread_tracker.thread_completed(
                            thread_id, success=False
                        )
                        thread_tracker.thread_rejected()  # Count as rejected

            except Exception as e:
                duration = thread_tracker.thread_completed(thread_id, success=False)
                logger.error(
                    "trello_sync_failed",
                    duration_ms=int(duration * 1000) if duration is not None else None,
                    error=str(e),
                    error_type=type(e).__name__,
                    card_id=event_info.get("card_id"),
                    source="trello",
                    status="error",
                    exc_info=True,
                )

        # Submit to thread pool and attach error callback
        future = executor.submit(run_sync)
        def _log_future(f):
            try:
                _ = f.result()
            except Exception as e:
                logger.error(
                    "trello_sync_task_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    source="trello",
                    status="error",
                    exc_info=True,
                )
        future.add_done_callback(_log_future)
        logger.debug("trello_webhook_submitted", card_id=event_info.get("card_id"), source="trello")

    return "", 200


@trello_bp.route("/thread-stats")
def thread_stats():
    """Get thread statistics including sync lock info"""
    with thread_tracker.lock:
        stats = thread_tracker.stats.copy()

    return jsonify(stats)


def drain_trello_queue(max_items: int = 5):
    """Drain up to max_items from the Trello event queue when lock is free."""
    app = current_app._get_current_object()

    if sync_lock_manager.is_locked():
        return 0

    drained = 0

    while drained < max_items:
        try:
            event_info = trello_event_queue.get_nowait()
        except Empty:
            break

        def run_sync_event(evt):
            thread_id = threading.current_thread().ident
            thread_tracker.thread_started(thread_id)
            try:
                with app.app_context():
                    try:
                        with sync_lock_manager.acquire_sync_lock("Trello-Queue"):
                            logger.info("trello_drain_sync_started", card_id=evt.get("card_id"), source="trello")
                            sync_from_trello(evt)
                            logger.info("trello_drain_sync_finished", card_id=evt.get("card_id"), source="trello")
                        duration = thread_tracker.thread_completed(thread_id, success=True)
                        logger.info(
                            "trello_drain_sync_completed",
                            duration_ms=int(duration * 1000),
                            card_id=evt.get("card_id"),
                            source="trello",
                            status="ok",
                        )
                    except RuntimeError as lock_error:
                        # Could not acquire (race); requeue and stop draining
                        logger.info(
                            "trello_drain_lock_contention",
                            error=str(lock_error),
                            error_type=type(lock_error).__name__,
                            card_id=evt.get("card_id"),
                            source="trello",
                            status="queued",
                        )
                        try:
                            trello_event_queue.put_nowait(evt)
                        except Full:
                            logger.warning(
                                "trello_drain_requeue_failed",
                                reason="queue_full",
                                card_id=evt.get("card_id"),
                                source="trello",
                            )
                        thread_tracker.thread_completed(thread_id, success=False)
                        return False
            except Exception as e:
                duration = thread_tracker.thread_completed(thread_id, success=False)
                logger.error(
                    "trello_drain_sync_failed",
                    duration_ms=int(duration * 1000) if duration is not None else None,
                    error=str(e),
                    error_type=type(e).__name__,
                    card_id=evt.get("card_id"),
                    source="trello",
                    status="error",
                    exc_info=True,
                )
                return True
            return True

        # Execute drained event in the pool to keep behavior consistent
        future = executor.submit(run_sync_event, event_info)
        drained += 1

    return drained
