"""Google OAuth access-token lifecycle helpers.

`get_valid_access_token(user_id)` returns a non-expired token, refreshing
via Google's /token endpoint when needed. Mirrors the proactive-buffer
pattern used in app/procore/procore_auth.py.
"""
from datetime import datetime

import requests
from flask import current_app

from app.logging_config import get_logger
from app.models import GoogleCredentials, db

logger = get_logger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKEN_REFRESH_BUFFER_SECONDS = 60


def post_token_request(data: dict, timeout: int = 5):
    """POST to Google's /token endpoint. Caller handles status / parsing."""
    return requests.post(GOOGLE_TOKEN_URL, data=data, timeout=timeout)


class GoogleAuthError(RuntimeError):
    """Base class for Google OAuth failures."""


class NoGoogleCredentialsError(GoogleAuthError):
    """User has not linked Google."""


class RefreshTokenMissingError(GoogleAuthError):
    """Stored credentials lack a refresh token; user must re-link."""


class RefreshTokenInvalidError(GoogleAuthError):
    """Google rejected our refresh token (revoked / expired)."""


def get_valid_access_token(user_id: int) -> str:
    """Return a non-expired Google access token for `user_id`.

    Refreshes via Google's /token endpoint if the stored token is within
    60 seconds of expiry. On `invalid_grant` (revoked grant), the row is
    deleted and `RefreshTokenInvalidError` is raised so the caller can
    surface a "please reconnect Gmail" prompt.
    """
    creds = GoogleCredentials.get_for_user(user_id)
    if creds is None:
        raise NoGoogleCredentialsError(f"user {user_id} has no Google credentials")

    if not creds.is_expired(buffer_seconds=TOKEN_REFRESH_BUFFER_SECONDS):
        return creds.access_token

    if not creds.refresh_token:
        raise RefreshTokenMissingError(
            f"user {user_id} has no refresh_token; re-link required"
        )

    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise GoogleAuthError("GOOGLE_CLIENT_ID/SECRET not configured")

    try:
        resp = post_token_request({
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        })
    except requests.RequestException as exc:
        logger.error("google_token_refresh_network_error", user_id=user_id, error=str(exc))
        raise GoogleAuthError(f"network error refreshing token: {exc}") from exc

    if resp.status_code in (400, 401):
        body = resp.json() if resp.content else {}
        if body.get("error") == "invalid_grant":
            logger.warning(
                "google_token_invalid_grant_deleting_creds",
                user_id=user_id,
                google_sub=creds.google_sub,
            )
            db.session.delete(creds)
            user = creds.user
            if user is not None:
                user.google_sub = None
            db.session.commit()
            raise RefreshTokenInvalidError("refresh_token rejected by Google")
        logger.error(
            "google_token_refresh_failed",
            user_id=user_id,
            status=resp.status_code,
            error=body.get("error"),
        )
        raise GoogleAuthError(f"refresh failed: {body.get('error')}")

    resp.raise_for_status()
    token = resp.json()
    creds.update_from_token_response(token)
    db.session.commit()
    logger.info(
        "google_token_refreshed",
        user_id=user_id,
        expires_at=creds.token_expires_at.isoformat(),
    )
    return creds.access_token
