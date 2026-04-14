"""
@milehigh-header
schema_version: 1
purpose: Provide a singleton ProcoreAPI instance configured for the current environment (production, sandbox, or local).
exports:
  get_procore_client: Returns the singleton ProcoreAPI instance, creating it on first call.
imports_from: [os, app.procore.api, app.logging_config, app.config]
imported_by: [app/procore/__init__.py, app/procore/procore.py, app/procore/webhook_utils.py, app/admin/__init__.py, app/brain/drafting_work_load/routes.py, app/procore/scripts/check.py, app/procore/scripts/create.py, app/procore/scripts/delete.py]
invariants:
  - The client is a module-level singleton; once created it is reused for the process lifetime.
  - Webhook URL is chosen based on FLASK_ENV / ENVIRONMENT env var (production, sandbox, or dev fallback).
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
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
