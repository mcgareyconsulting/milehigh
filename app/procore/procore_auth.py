import requests
from datetime import datetime, timedelta
from app.config import Config as cfg
from app.models import db, ProcoreToken

CLIENT_ID = cfg.PROD_PROCORE_CLIENT_ID
CLIENT_SECRET = cfg.PROD_PROCORE_CLIENT_SECRET
TOKEN_URL = "https://login.procore.com/oauth/token"
TOKEN_REFRESH_BUFFER_SECONDS = 60

def _request_client_credentials_token():
    """Request a new OAuth access token via client credentials flow."""
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    response = requests.post(TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    token_type = data.get("token_type", "Bearer")
    return access_token, expires_in, token_type

def get_access_token():
    """Return a valid Procore access token, refreshing with client credentials if needed."""
    return _ensure_token().access_token

def get_access_token_force_refresh():
    """Force retrieval of a fresh Procore access token."""
    return _ensure_token(force_refresh=True).access_token

def _ensure_token(force_refresh: bool = False) -> ProcoreToken:
    auth = ProcoreToken.get_current()
    needs_refresh = force_refresh or auth is None or _is_expiring(auth)

    if needs_refresh:
        access_token, expires_in, token_type = _request_client_credentials_token()
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        auth = _persist_token(access_token, expires_at, token_type)

    return auth

def _persist_token(access_token: str, expires_at: datetime, token_type: str) -> ProcoreToken:
    auth = ProcoreToken.get_current()
    if auth is None:
        auth = ProcoreToken(access_token=access_token, expires_at=expires_at)
        db.session.add(auth)
    else:
        auth.access_token = access_token
        auth.expires_at = expires_at
    auth.refresh_token = ""
    auth.token_type = token_type or "Bearer"
    auth.updated_at = datetime.utcnow()
    db.session.commit()
    return auth

def _is_expiring(auth: ProcoreToken) -> bool:
    buffer_time = datetime.utcnow() + timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS)
    return auth.expires_at is None or auth.expires_at <= buffer_time

def initialize_tokens():
    """Manually fetch and store a Procore access token (utility for scripts)."""
    access_token, expires_in, token_type = _request_client_credentials_token()
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    _persist_token(access_token, expires_at, token_type)


if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        initialize_tokens()