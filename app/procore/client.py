import os
from app.procore.api import ProcoreAPI
from app.logging_config import get_logger

logger = get_logger(__name__)

_client = None


def get_procore_client():
    """Returns a singleton instance of the ProcoreAPI class"""
    global _client
    if _client is None:
        from app.config import Config as cfg

        env = (os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")).lower()

        if env in ("production", "prod"):
            webhook_url = cfg.PROCORE_PROD_WEBHOOK_URL
        elif env in ("sandbox", "staging", "stage"):
            webhook_url = cfg.PROCORE_SANDBOX_WEBHOOK_URL
        else:
            webhook_url = cfg.PROCORE_DEV_WEBHOOK_URL

        logger.info("Procore client initialised", environment=env, webhook_url=webhook_url)

        _client = ProcoreAPI(
            cfg.PROD_PROCORE_CLIENT_ID,
            cfg.PROD_PROCORE_CLIENT_SECRET,
            webhook_url,
        )
    return _client
