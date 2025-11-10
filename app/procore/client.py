from app.procore.api import ProcoreAPI
_client = None

def get_procore_client():
    '''
    Returns a singleton instance of the ProcoreAPI class
    '''
    global _client
    if _client is None:
        from app.config import Config as cfg
        _client = ProcoreAPI(cfg.PROD_PROCORE_CLIENT_ID, cfg.PROD_PROCORE_CLIENT_SECRET, cfg.PROCORE_DEV_WEBHOOK_URL)
    return _client