from app.procore.api import ProcoreAPI
_client = None

def get_procore_client():
    '''
    Returns a singleton instance of the ProcoreAPI class
    '''
    global _client
    if _client is None:
        from app.config import Config as cfg
        # Dev
        # _client = ProcoreAPI(cfg.PROD_PROCORE_CLIENT_ID, cfg.PROD_PROCORE_CLIENT_SECRET, cfg.PROCORE_DEV_WEBHOOK_URL)
        # Prod
        _client = ProcoreAPI(cfg.PROD_PROCORE_CLIENT_ID, cfg.PROD_PROCORE_CLIENT_SECRET, cfg.PROCORE_PROD_WEBHOOK_URL)
        # Sandbox
        # _client = ProcoreAPI(cfg.PROD_PROCORE_CLIENT_ID, cfg.PROD_PROCORE_CLIENT_SECRET, cfg.PROCORE_SANDBOX_WEBHOOK_URL)
    return _client