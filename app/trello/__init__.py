from flask import Blueprint, request, current_app, jsonify
from app.trello.utils import parse_webhook_data
from app.trello.sync import sync_from_trello
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


# Global tracker and thread pool
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
            action_type = event_info.get("action_type", "unknown")
            app.logger.debug(f"Skipping unhandled webhook: {action_type}")
            return "", 200

        # Log Trello webhook receipt with userId when available
        trello_user_id = event_info.get("trello_user_id")
        app.logger.info(
            "Trello webhook received: event=%s, card_id=%s, trello_user_id=%s",
            event_info.get("event"),
            event_info.get("card_id"),
            trello_user_id,
        )

        def run_sync():
            thread_id = threading.current_thread().ident
            thread_tracker.thread_started(thread_id)

            try:
                with app.app_context():
                    app.logger.info("Trello sync started")
                    sync_from_trello(event_info)
                    app.logger.info("Trello sync completed successfully")

                duration = thread_tracker.thread_completed(thread_id, success=True)
                app.logger.info(f"Sync completed in {duration:.2f}s")

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

    return jsonify(stats)
