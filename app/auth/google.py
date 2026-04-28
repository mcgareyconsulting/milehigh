"""Google OAuth — Connect Gmail to an already-logged-in user.

Authentication remains password-only. This module is a per-feature link flow:
the user logs in with their MHMW password, then opts in to attach Gmail
readonly so Banana Boy can read recent threads. The OAuth dance never creates
or logs in users — it only attaches credentials to the current session.

Tokens never leave the server. The frontend sees only `gmail_linked` via /me.
"""
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from authlib.integrations.requests_client import OAuth2Session
from flask import current_app, redirect, request, session
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token

from app.auth.routes import auth_bp
from app.auth.utils import get_current_user
from app.logging_config import get_logger
from app.models import GoogleCredentials, db

logger = get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SESSION_KEY = "google_oauth"
STATE_TTL_SECONDS = 600
DEFAULT_NEXT = "/job-log"


def _validate_next(path, default=DEFAULT_NEXT):
    """Allow same-origin paths only — block open-redirect via `next=https://...`."""
    if not path:
        return default
    if not isinstance(path, str):
        return default
    if not path.startswith("/") or path.startswith("//"):
        return default
    return path


def _validate_origin(origin):
    """Allow only http(s)://host[:port] — same shape browsers send in Origin header."""
    if not origin or not isinstance(origin, str):
        return None
    if not (origin.startswith("http://") or origin.startswith("https://")):
        return None
    if "/" in origin[8:]:
        return None
    return origin


def _frontend_redirect(path, **params):
    """Redirect to a frontend route. Uses the origin captured at /initiate time
    (stored in session) so the callback returns to the Vite dev server in dev,
    not Flask's own port. Falls back to a relative redirect when no origin is
    stored — that's the same-origin production case.
    """
    stored = session.get(SESSION_KEY) or {}
    origin = _validate_origin(stored.get("origin"))
    target = f"{origin}{path}" if origin else path
    if params:
        return redirect(f"{target}?{urlencode(params)}")
    return redirect(target)


def _safe_redirect_with_error(error_code, next_path=DEFAULT_NEXT, **extras):
    """Redirect back to the originating page with a google_error code."""
    response = _frontend_redirect(next_path, google_error=error_code, **extras)
    session.pop(SESSION_KEY, None)
    return response


def _build_authorization_url(nonce, login_hint=None):
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    redirect_uri = current_app.config["GOOGLE_REDIRECT_URI"]
    scopes = current_app.config["GOOGLE_OAUTH_SCOPES"]

    oauth = OAuth2Session(client_id=client_id, scope=" ".join(scopes))
    extra = {
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": nonce,
    }
    if login_hint:
        extra["login_hint"] = login_hint
    auth_url, _ = oauth.create_authorization_url(
        GOOGLE_AUTH_URL,
        redirect_uri=redirect_uri,
        **extra,
    )
    return auth_url


def _exchange_code_for_tokens(code):
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    client_secret = current_app.config["GOOGLE_CLIENT_SECRET"]
    redirect_uri = current_app.config["GOOGLE_REDIRECT_URI"]

    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _verify_id_token(id_token_str):
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    return google_id_token.verify_oauth2_token(
        id_token_str, google_auth_requests.Request(), client_id
    )


def _scopes_include_gmail_readonly(scopes_str):
    if not scopes_str:
        return False
    return "https://www.googleapis.com/auth/gmail.readonly" in scopes_str.split()


def _upsert_credentials(user_id, token, idinfo):
    """Create or update the user's google_credentials row from the token + id_token claims."""
    expires_in = int(token.get("expires_in", 3600))
    creds = GoogleCredentials.get_for_user(user_id)
    if creds is None:
        creds = GoogleCredentials(
            user_id=user_id,
            provider="google",
            google_sub=idinfo["sub"],
            email=idinfo.get("email", ""),
            email_verified=bool(idinfo.get("email_verified", True)),
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            token_expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
            scopes=token.get("scope", ""),
            id_token=token.get("id_token"),
        )
        db.session.add(creds)
    else:
        creds.google_sub = idinfo["sub"]
        creds.email = idinfo.get("email", creds.email)
        creds.email_verified = bool(idinfo.get("email_verified", True))
        creds.access_token = token["access_token"]
        if token.get("refresh_token"):
            creds.refresh_token = token["refresh_token"]
        creds.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        creds.scopes = token.get("scope", creds.scopes)
        if token.get("id_token"):
            creds.id_token = token["id_token"]
    return creds


@auth_bp.route("/google/initiate", methods=["GET"])
def initiate_google_oauth():
    next_path = _validate_next(request.args.get("next"))

    current_user = get_current_user()
    if current_user is None:
        return _frontend_redirect("/login", google_error="login_required")

    if not current_app.config.get("GOOGLE_CLIENT_ID"):
        logger.error("google_oauth_not_configured")
        return _frontend_redirect(next_path, google_error="not_configured")

    nonce = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(seconds=STATE_TTL_SECONDS)).isoformat()
    # Capture the frontend origin so the callback redirects back to the Vite
    # dev server rather than Flask's own host. In production these are the
    # same origin so this is a no-op.
    origin_header = request.headers.get("Origin") or request.headers.get("Referer", "")
    if origin_header.startswith(("http://", "https://")):
        # Strip any path component from a Referer-style URL.
        scheme_host = origin_header.split("/", 3)
        origin_value = "/".join(scheme_host[:3]) if len(scheme_host) >= 3 else None
    else:
        origin_value = None
    session[SESSION_KEY] = {
        "nonce": nonce,
        "next": next_path,
        "expires_at": expires_at,
        "origin": _validate_origin(origin_value),
    }

    auth_url = _build_authorization_url(
        nonce, login_hint=current_user.email or current_user.username
    )
    return redirect(auth_url)


@auth_bp.route("/google/callback", methods=["GET"])
def google_oauth_callback():
    stored = session.get(SESSION_KEY) or {}
    next_path = stored.get("next") or DEFAULT_NEXT

    google_error = request.args.get("error")
    if google_error:
        logger.info("google_oauth_user_cancelled", error=google_error)
        return _safe_redirect_with_error(google_error, next_path)

    state = request.args.get("state")
    code = request.args.get("code")

    if not stored or not state or state != stored.get("nonce"):
        return _safe_redirect_with_error("state_mismatch", next_path)
    try:
        if datetime.fromisoformat(stored["expires_at"]) < datetime.utcnow():
            return _safe_redirect_with_error("state_expired", next_path)
    except (KeyError, ValueError):
        return _safe_redirect_with_error("state_mismatch", next_path)

    if not code:
        return _safe_redirect_with_error("missing_code", next_path)

    try:
        token = _exchange_code_for_tokens(code)
    except requests.RequestException as exc:
        logger.error("google_token_exchange_failed", error=str(exc))
        return _safe_redirect_with_error("token_exchange_failed", next_path)

    if not _scopes_include_gmail_readonly(token.get("scope", "")):
        logger.warning("google_oauth_scope_missing", granted_scope=token.get("scope"))
        return _safe_redirect_with_error("scope_missing", next_path)

    id_token_str = token.get("id_token")
    if not id_token_str:
        return _safe_redirect_with_error("missing_id_token", next_path)
    try:
        idinfo = _verify_id_token(id_token_str)
    except ValueError as exc:
        logger.error("google_id_token_invalid", error=str(exc))
        return _safe_redirect_with_error("invalid_id_token", next_path)

    if not idinfo.get("email_verified", False):
        return _safe_redirect_with_error("email_unverified", next_path)

    google_sub = idinfo["sub"]
    google_email = (idinfo.get("email") or "").lower()

    current_user = get_current_user()
    if current_user is None:
        return _safe_redirect_with_error("session_lost", next_path)

    existing = GoogleCredentials.query.filter_by(google_sub=google_sub).first()
    if existing is not None and existing.user_id != current_user.id:
        logger.warning(
            "google_link_conflict",
            current_user_id=current_user.id,
            existing_user_id=existing.user_id,
        )
        return _safe_redirect_with_error("already_linked_other_user", next_path)

    current_user.google_sub = google_sub
    if not current_user.email:
        current_user.email = google_email
    _upsert_credentials(current_user.id, token, idinfo)
    db.session.commit()

    logger.info(
        "google_link_success", user_id=current_user.id, email=google_email
    )
    response = _frontend_redirect(next_path, gmail_connected="1")
    session.pop(SESSION_KEY, None)
    return response
