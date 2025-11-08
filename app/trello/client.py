from app.trello.api import TrelloAPI

_client = None

def get_trello_client():
    '''
    Returns a singleton instance of the TrelloAPI class.
    '''
    global _client
    if _client is None:
        from app.config import Config as cfg
        _client = TrelloAPI(cfg.TRELLO_API_KEY, cfg.TRELLO_TOKEN)
    return _client