"""Microsoft OAuth — Connect Outlook to an already-logged-in user.

Per-feature link flow mirroring app/auth/google.py. The user logs in with
their MHMW password, then opts in to attach Microsoft Graph (Mail.Read +
offline_access) so Banana Boy can read recent Outlook threads during a
report deep dive.

The OAuth dance never creates or logs in users — it only attaches credentials
to the current session. Tokens never leave the server. The frontend sees
only `outlook_linked` via /me.
"""
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

import requests
from authlib.integrations.requests_client import OAuth2Session
from flask import current_app, redirect, request, session

from app.auth.microsoft_tokens import post_token_request
from app.auth.routes import auth_bp
from app.auth.utils import get_current_user
from app.logging_config import get_logger
from app.models import MicrosoftCredentials, db

logger = get_logger(__name__)

SESSION_KEY = "microsoft_oauth"
STATE_TTL_SECONDS = 600
DEFAULT_NEXT = "/job-log"
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"
REQUIRED_MAIL_SCOPES = {"Mail.Read", "https://graph.microsoft.com/Mail.Read"}


def _authorize_url() -> str:
    tenant = current_app.config.get("MS_TENANT", "common")
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"


def _validate_next(path, default=DEFAULT_NEXT):
    if not path or not isinstance(path, str):
        return default
    if not path.startswith("/") or path.startswith("//"):
        return default
    return path


def _validate_origin(origin):
    if not origin or not isinstance(origin, str):
        return None
    if not (origin.startswith("http://") or origin.startswith("https://")):
        return None
    if "/" in origin[8:]:
        return None
    return origin


def _frontend_redirect(path, **params):
    stored = session.get(SESSION_KEY) or {}
    origin = _validate_origin(stored.get("origin"))
    target = f"{origin}{path}" if origin else path
    if params:
        return redirect(f"{target}?{urlencode(params)}")
    return redirect(target)


def _safe_redirect_with_error(error_code, next_path=DEFAULT_NEXT, **extras):
    response = _frontend_redirect(next_path, ms_error=error_code, **extras)
    session.pop(SESSION_KEY, None)
    return response


def _build_authorization_url(nonce, login_hint=None):
    client_id = current_app.config["MS_CLIENT_ID"]
    redirect_uri = current_app.config["MS_REDIRECT_URI"]
    scopes = current_app.config["MS_OAUTH_SCOPES"]

    oauth = OAuth2Session(client_id=client_id, scope=" ".join(scopes))
    extra = {
        "response_mode": "query",
        "prompt": "select_account",
        "state": nonce,
    }
    if login_hint:
        extra["login_hint"] = login_hint
    auth_url, _ = oauth.create_authorization_url(
        _authorize_url(),
        redirect_uri=redirect_uri,
        **extra,
    )
    return auth_url


def _exchange_code_for_tokens(code):
    scopes = current_app.config["MS_OAUTH_SCOPES"]
    resp = post_token_request({
        "code": code,
        "client_id": current_app.config["MS_CLIENT_ID"],
        "client_secret": current_app.config["MS_CLIENT_SECRET"],
        "redirect_uri": current_app.config["MS_REDIRECT_URI"],
        "grant_type": "authorization_code",
        "scope": " ".join(scopes),
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _scopes_include_mail_read(scopes_str):
    if not scopes_str:
        return False
    granted = set(scopes_str.split())
    return bool(granted & REQUIRED_MAIL_SCOPES)


def _fetch_graph_profile(access_token):
    """Call Graph /me to retrieve oid, mail/upn, tenant id. Caller handles errors."""
    resp = requests.get(
        GRAPH_ME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()


def _upsert_credentials(user_id, token, profile):
    expires_in = int(token.get("expires_in", 3600))
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    creds = MicrosoftCredentials.get_for_user(user_id)
    is_new = creds is None
    email = (profile.get("mail") or profile.get("userPrincipalName") or "").lower()
    if is_new:
        creds = MicrosoftCredentials(
            user_id=user_id,
            provider="microsoft",
            ms_oid=profile["id"],
            email=email or "",
        )
        db.session.add(creds)

    creds.ms_oid = profile["id"]
    creds.email = email or creds.email
    creds.tenant_id = profile.get("tenantId") or creds.tenant_id
    creds.access_token = token["access_token"]
    creds.token_expires_at = expires_at
    creds.scopes = token.get("scope", creds.scopes if not is_new else "")
    if token.get("refresh_token"):
        creds.refresh_token = token["refresh_token"]
    return creds


@auth_bp.route("/microsoft/initiate", methods=["GET"])
def initiate_microsoft_oauth():
    next_path = _validate_next(request.args.get("next"))

    current_user = get_current_user()
    if current_user is None:
        return _frontend_redirect("/login", ms_error="login_required")

    if not current_app.config.get("MS_CLIENT_ID"):
        logger.error("ms_oauth_not_configured")
        return _frontend_redirect(next_path, ms_error="not_configured")

    nonce = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(seconds=STATE_TTL_SECONDS)).isoformat()
    raw_origin = request.headers.get("Origin") or request.headers.get("Referer", "")
    parsed = urlsplit(raw_origin) if raw_origin else None
    origin_value = (
        f"{parsed.scheme}://{parsed.netloc}"
        if parsed and parsed.scheme in ("http", "https") and parsed.netloc
        else None
    )
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


@auth_bp.route("/microsoft/callback", methods=["GET"])
def microsoft_oauth_callback():
    stored = session.get(SESSION_KEY) or {}
    next_path = stored.get("next") or DEFAULT_NEXT

    ms_error = request.args.get("error")
    if ms_error:
        logger.info("ms_oauth_user_cancelled", error=ms_error)
        return _safe_redirect_with_error(ms_error, next_path)

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
        logger.error("ms_token_exchange_failed", error=str(exc))
        return _safe_redirect_with_error("token_exchange_failed", next_path)

    if not _scopes_include_mail_read(token.get("scope", "")):
        logger.warning("ms_oauth_scope_missing", granted_scope=token.get("scope"))
        return _safe_redirect_with_error("scope_missing", next_path)

    try:
        profile = _fetch_graph_profile(token["access_token"])
    except requests.RequestException as exc:
        logger.error("ms_graph_profile_failed", error=str(exc))
        return _safe_redirect_with_error("profile_fetch_failed", next_path)

    if not profile.get("id"):
        return _safe_redirect_with_error("profile_invalid", next_path)

    current_user = get_current_user()
    if current_user is None:
        return _safe_redirect_with_error("session_lost", next_path)

    existing = MicrosoftCredentials.query.filter_by(ms_oid=profile["id"]).first()
    if existing is not None and existing.user_id != current_user.id:
        logger.warning(
            "ms_link_conflict",
            current_user_id=current_user.id,
            existing_user_id=existing.user_id,
        )
        return _safe_redirect_with_error("already_linked_other_user", next_path)

    _upsert_credentials(current_user.id, token, profile)
    db.session.commit()

    logger.info(
        "ms_link_success",
        user_id=current_user.id,
        email=(profile.get("mail") or profile.get("userPrincipalName") or "").lower(),
    )
    response = _frontend_redirect(next_path, outlook_connected="1")
    session.pop(SESSION_KEY, None)
    return response


@auth_bp.route("/microsoft/disconnect", methods=["POST"])
def disconnect_microsoft():
    current_user = get_current_user()
    if current_user is None:
        return {"error": "Not authenticated"}, 401
    creds = MicrosoftCredentials.get_for_user(current_user.id)
    if creds is None:
        return {"status": "not_linked"}, 200
    db.session.delete(creds)
    db.session.commit()
    logger.info("ms_disconnect", user_id=current_user.id)
    return {"status": "disconnected"}, 200
