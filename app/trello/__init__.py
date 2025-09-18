from flask import Blueprint, request, current_app
from app.sync import sync_from_trello
from app.trello.utils import parse_webhook_data
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

        def run_sync():
            thread_id = threading.current_thread().ident
            thread_tracker.thread_started(thread_id)

            try:
                with app.app_context():
                    sync_from_trello(event_info)
                duration = thread_tracker.thread_completed(thread_id, success=True)
                app.logger.info(f"Sync completed in {duration:.2f}s")
            except Exception as e:
                duration = thread_tracker.thread_completed(thread_id, success=False)
                app.logger.error(f"Sync failed after {duration:.2f}s: {e}")

        executor.submit(run_sync)

    return "", 200


@trello_bp.route("/thread-stats")
def thread_stats():
    with thread_tracker.lock:
        stats = thread_tracker.stats.copy()
    return stats
