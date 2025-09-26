from flask import Blueprint, request, current_app, jsonify
from app.sync import sync_from_trello
from app.trello.utils import parse_webhook_data
from app.sync_lock import sync_lock_manager  # Add this import
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from queue import Queue, Full, Empty
import time


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


# Global tracker
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
        data = request.json
        event_info = parse_webhook_data(data)
        app = current_app._get_current_object()

        # Skip unhandled webhooks
        if not event_info.get("handled"):
            app.logger.info(f"Skipping unhandled webhook: {event_info}")
            return "", 200

        # If locked, enqueue the event for later processing and return 202
        if sync_lock_manager.is_locked():
            try:
                trello_event_queue.put_nowait(event_info)
                thread_tracker.thread_rejected()
                app.logger.info("Trello webhook queued due to active lock")
                return jsonify({"status": "queued"}), 202
            except Full:
                thread_tracker.thread_rejected()
                app.logger.warning("Trello event queue is full; dropping event")
                return jsonify({"status": "overloaded"}), 429

        def run_sync():
            thread_id = threading.current_thread().ident
            thread_tracker.thread_started(thread_id)

            try:
                with app.app_context():
                    # Try to acquire the sync lock in the thread
                    try:
                        with sync_lock_manager.acquire_sync_lock("Trello-Hook"):
                            app.logger.info("Trello sync started with lock acquired")
                            sync_from_trello(
                                event_info
                            )  # Remove any @synchronized_sync from this function
                            app.logger.info("Trello sync completed successfully")

                        duration = thread_tracker.thread_completed(
                            thread_id, success=True
                        )
                        app.logger.info(f"Sync completed in {duration:.2f}s")

                    except RuntimeError as lock_error:
                        # Lock acquisition failed - this shouldn't happen since we checked above
                        # but it's possible another sync started between the check and thread execution
                        app.logger.warning(
                            f"Trello sync lock acquisition failed in thread: {lock_error}"
                        )
                        duration = thread_tracker.thread_completed(
                            thread_id, success=False
                        )
                        thread_tracker.thread_rejected()  # Count as rejected

            except Exception as e:
                duration = thread_tracker.thread_completed(thread_id, success=False)
                app.logger.error(f"Sync failed after {duration:.2f}s: {e}")

        # Submit to thread pool and attach error callback
        future = executor.submit(run_sync)
        def _log_future(f):
            try:
                _ = f.result()
            except Exception as e:
                app.logger.error(f"Trello sync task failed: {e}")
        future.add_done_callback(_log_future)
        app.logger.info("Trello webhook submitted to thread pool")

    return "", 200


@trello_bp.route("/thread-stats")
def thread_stats():
    """Get thread statistics including sync lock info"""
    with thread_tracker.lock:
        stats = thread_tracker.stats.copy()

    # Add sync lock status
    stats.update(
        {
            "sync_locked": sync_lock_manager.is_locked(),
            "current_operation": sync_lock_manager.get_current_operation(),
            "queue_size": 0,  # You don't have queuing yet
        }
    )

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
                            app.logger.info("Drained Trello event started with lock acquired")
                            sync_from_trello(evt)
                            app.logger.info("Drained Trello event completed successfully")
                        duration = thread_tracker.thread_completed(thread_id, success=True)
                        app.logger.info(f"Drained sync completed in {duration:.2f}s")
                    except RuntimeError as lock_error:
                        # Could not acquire (race); requeue and stop draining
                        app.logger.info(f"Queue drain lock contention: {lock_error}")
                        try:
                            trello_event_queue.put_nowait(evt)
                        except Full:
                            app.logger.warning("Queue full while requeuing drained event; dropping")
                        thread_tracker.thread_completed(thread_id, success=False)
                        return False
            except Exception as e:
                duration = thread_tracker.thread_completed(thread_id, success=False)
                app.logger.error(f"Drained sync failed after {duration:.2f}s: {e}")
                return True
            return True

        # Execute drained event in the pool to keep behavior consistent
        future = executor.submit(run_sync_event, event_info)
        drained += 1

    return drained
