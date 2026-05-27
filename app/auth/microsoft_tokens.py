"""Microsoft (Entra ID) OAuth access-token lifecycle helpers.

`get_valid_access_token(user_id)` returns a non-expired token, refreshing
via Microsoft's /token endpoint when needed. Mirrors app/auth/google_tokens.py.
"""
from datetime import datetime

import requests
from flask import current_app

from app.logging_config import get_logger
from app.models import MicrosoftCredentials, db

logger = get_logger(__name__)

TOKEN_REFRESH_BUFFER_SECONDS = 60


def _token_url() -> str:
    tenant = current_app.config.get("MS_TENANT", "common")
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def post_token_request(data: dict, timeout: int = 5):
    """POST to Microsoft's /token endpoint. Caller handles status / parsing."""
    return requests.post(_token_url(), data=data, timeout=timeout)


class MicrosoftAuthError(RuntimeError):
    """Base class for Microsoft OAuth failures."""


class NoMicrosoftCredentialsError(MicrosoftAuthError):
    """User has not linked Microsoft."""


class RefreshTokenMissingError(MicrosoftAuthError):
    """Stored credentials lack a refresh token; user must re-link."""


class RefreshTokenInvalidError(MicrosoftAuthError):
    """Microsoft rejected our refresh token (revoked / expired / consent withdrawn)."""


def get_valid_access_token(user_id: int) -> str:
    """Return a non-expired Microsoft Graph access token for `user_id`.

    Refreshes via Microsoft's /token endpoint if the stored token is within
    60 seconds of expiry. On `invalid_grant`, the row is deleted and
    `RefreshTokenInvalidError` is raised so the caller can surface a
    "please reconnect Outlook" prompt.
    """
    creds = MicrosoftCredentials.get_for_user(user_id)
    if creds is None:
        raise NoMicrosoftCredentialsError(f"user {user_id} has no Microsoft credentials")

    if not creds.is_expired(buffer_seconds=TOKEN_REFRESH_BUFFER_SECONDS):
        return creds.access_token

    if not creds.refresh_token:
        raise RefreshTokenMissingError(
            f"user {user_id} has no refresh_token; re-link required"
        )

    client_id = current_app.config.get("MS_CLIENT_ID")
    client_secret = current_app.config.get("MS_CLIENT_SECRET")
    scopes = current_app.config.get("MS_OAUTH_SCOPES") or []
    if not client_id or not client_secret:
        raise MicrosoftAuthError("MS_CLIENT_ID/SECRET not configured")

    try:
        resp = post_token_request({
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": " ".join(scopes),
        })
    except requests.RequestException as exc:
        logger.error("ms_token_refresh_network_error", user_id=user_id, error=str(exc))
        raise MicrosoftAuthError(f"network error refreshing token: {exc}") from exc

    if resp.status_code in (400, 401):
        body = resp.json() if resp.content else {}
        if body.get("error") == "invalid_grant":
            logger.warning(
                "ms_token_invalid_grant_deleting_creds",
                user_id=user_id,
                ms_oid=creds.ms_oid,
            )
            db.session.delete(creds)
            db.session.commit()
            raise RefreshTokenInvalidError("refresh_token rejected by Microsoft")
        logger.error(
            "ms_token_refresh_failed",
            user_id=user_id,
            status=resp.status_code,
            error=body.get("error"),
            description=body.get("error_description"),
        )
        raise MicrosoftAuthError(f"refresh failed: {body.get('error')}")

    resp.raise_for_status()
    token = resp.json()
    creds.update_from_token_response(token)
    db.session.commit()
    logger.info(
        "ms_token_refreshed",
        user_id=user_id,
        expires_at=creds.token_expires_at.isoformat(),
    )
    return creds.access_token
