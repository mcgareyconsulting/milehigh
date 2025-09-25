from flask import Blueprint, request, current_app, jsonify
from app.sync import sync_from_trello
from app.trello.utils import parse_webhook_data
from app.sync_lock import sync_lock_manager  # Add this import
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
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

        # Check if sync is locked BEFORE submitting to thread pool
        if sync_lock_manager.is_locked():
            current_op = sync_lock_manager.get_current_operation()
            thread_tracker.thread_rejected()
            app.logger.warning(
                f"Trello webhook rejected - sync locked by: {current_op}"
            )

            # Return HTTP 423 to tell Trello to retry later
            return (
                jsonify(
                    {
                        "status": "locked",
                        "message": f"Sync currently locked by: {current_op}",
                        "retry_after": 30,
                    }
                ),
                423,
            )

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

        # Submit to thread pool
        future = executor.submit(run_sync)
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
