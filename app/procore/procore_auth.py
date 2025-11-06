import os
import requests
from datetime import datetime, timedelta
from app.models import db, ProcoreToken
from app.config import Config as cfg
from app import create_app

CLIENT_ID = cfg.PROD_PROCORE_CLIENT_ID
CLIENT_SECRET = cfg.PROD_PROCORE_CLIENT_SECRET

def get_access_token():
    """Return a valid Procore access token, refreshing if expired."""
    auth = ProcoreToken.get_current()
    if not auth:
        raise Exception("No Procore tokens stored yet.")

    # If expired, refresh automatically
    if auth.expires_at <= datetime.utcnow():
        print("Refreshing Procore access token...")
        auth = refresh_tokens(auth)

    return auth.access_token


def refresh_tokens(auth):
    """Refresh and update stored tokens."""
    url = "https://login.procore.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": auth.refresh_token,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    }

    response = requests.post(url, data=data)
    response.raise_for_status()
    data = response.json()

    # Update tokens
    auth.access_token = data["access_token"]
    auth.refresh_token = data["refresh_token"]
    auth.token_type = data["token_type"]
    auth.expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"])
    auth.updated_at = datetime.utcnow()

    db.session.commit()
    return auth

def store_initial_tokens(access_token, refresh_token, expires_in):
    auth = ProcoreToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
    )
    db.session.add(auth)
    db.session.commit()


# if __name__ == "__main__":
#     app = create_app()
#     with app.app_context():
#         store_initial_tokens(cfg.PROD_PROCORE_ACCESS_TOKEN, cfg.PROD_PROCORE_REFRESH_TOKEN, 3600)
#         print("Initial Procore tokens stored in database")