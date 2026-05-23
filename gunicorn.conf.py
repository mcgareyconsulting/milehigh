import logging
from gunicorn import glogging

# Paths to suppress from access logs when the response is 200.
# Non-200 responses (errors, auth failures) are still logged.
_QUIET_PATHS = {'/brain/notifications/unread-count'}


class _QuietPathFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return not (any(p in msg for p in _QUIET_PATHS) and '" 200 ' in msg)


class Logger(glogging.Logger):
    def setup(self, cfg):
        super().setup(cfg)
        self.access_log.addFilter(_QuietPathFilter())
