import logging
from gunicorn import glogging

# Paths to suppress from access logs when the response is 200.
# Non-200 responses (errors, auth failures) are still logged.
_QUIET_PATHS = {'/brain/notifications/unread-count', '/brain/jobs?since='}


class _QuietPathFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return not (any(p in msg for p in _QUIET_PATHS) and '" 200 ' in msg)


class Logger(glogging.Logger):
    def setup(self, cfg):
        super().setup(cfg)
        self.access_log.addFilter(_QuietPathFilter())


logger_class = Logger


# --- Worker shape / timeouts -------------------------------------------------
# Photo uploads from phones over LTE can take well over the default 30s just to
# stream the request body. With the default `sync` worker the arbiter kills the
# worker mid-read (CRITICAL WORKER TIMEOUT -> gunicorn's own HTML 500, seen in
# prod 2026-08-24 on POST /brain/releases/<id>/photos). `gthread` heartbeats
# from its main loop, so a single slow request no longer trips the timeout, and
# the larger timeout covers genuinely long uploads. Still ONE process: the
# per-process sync_lock / thread pool assumptions in the app hold.
workers = 1
worker_class = "gthread"
threads = 4
timeout = 120
graceful_timeout = 30
keepalive = 5
