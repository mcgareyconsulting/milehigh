import threading
import requests
from datetime import datetime, timezone
from flask import current_app
from app.logging_config import get_logger

logger = get_logger(__name__)


class DevWebhookService:
    """Fire-and-forget webhook that forwards board events to an external server."""

    @staticmethod
    def send(event_type, payload):
        url = current_app.config.get('DEV_WEBHOOK_URL')
        if not url:
            return

        data = {
            'event': event_type,
            'data': payload,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        def _post():
            try:
                requests.post(url, json=data, timeout=5)
            except Exception as e:
                logger.warning("dev_webhook_failed", event=event_type, error=str(e))

        threading.Thread(target=_post, daemon=True).start()
