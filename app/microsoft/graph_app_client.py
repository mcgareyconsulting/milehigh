"""Microsoft Graph app-only (client-credentials) client.

App-only access scoped to a single mailbox/calendar (e.g. bb@mhmw.com) via an
Azure ApplicationAccessPolicy — the deliberate workaround for not opening Graph
across the whole org. No user logs in; we request an application token with the
existing AZURE_* app registration and call Graph as the application.

App-only tokens carry no refresh token, so the token is cached in-process with
its expiry and re-requested when stale (or once on a 401). Mirrors the Procore
client-credentials pattern in app/procore/procore_auth.py.
"""
import threading
from datetime import datetime, timedelta

import requests

from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_REFRESH_BUFFER_SECONDS = 60
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3

_token_lock = threading.Lock()
_cached_token = {"access_token": None, "expires_at": None}


def _token_url():
    return f"https://login.microsoftonline.com/{cfg.AZURE_TENANT_ID}/oauth2/v2.0/token"


def _request_app_token():
    """Fetch a fresh app-only token. Returns (access_token, expires_in_seconds)."""
    resp = requests.post(
        _token_url(),
        data={
            "grant_type": "client_credentials",
            "client_id": cfg.AZURE_CLIENT_ID,
            "client_secret": cfg.AZURE_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], int(data.get("expires_in", 3600))


def _is_expiring():
    exp = _cached_token["expires_at"]
    return exp is None or exp <= datetime.utcnow() + timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS)


def get_app_token(force_refresh=False):
    """Return a valid app-only Graph token, refreshing transparently when stale."""
    with _token_lock:
        if force_refresh or _cached_token["access_token"] is None or _is_expiring():
            access_token, expires_in = _request_app_token()
            _cached_token["access_token"] = access_token
            _cached_token["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)
            logger.info("graph_app_token_refreshed", expires_in=expires_in)
        return _cached_token["access_token"]


def graph_get(path, params=None, headers=None, timeout=DEFAULT_TIMEOUT, token_getter=None):
    """GET a Graph resource and return parsed JSON.

    Retries transient connection errors and forces a token refresh once on a
    401. `path` is relative to GRAPH_BASE (e.g. "/users/bb@mhmw.com/messages")
    or an absolute Graph URL (e.g. an @odata.nextLink).

    `headers` are merged over the defaults (Authorization/Accept) — used to add
    Graph's `Prefer` (e.g. an outlook timezone) on calendar reads.

    `token_getter` is a callable(force_refresh=bool) -> access_token. Defaults to
    the app-only token; a delegated client could pass its own.
    """
    token_getter = token_getter or get_app_token
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    force_refresh = False
    last_exc = None
    for attempt in range(MAX_RETRIES):
        token = token_getter(force_refresh=force_refresh)
        request_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        try:
            resp = requests.get(url, headers=request_headers, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            logger.warning("graph_get_transient", url=url, attempt=attempt, error=str(exc))
            continue
        if resp.status_code == 401:
            logger.warning("graph_get_401", url=url, attempt=attempt)
            last_exc = requests.HTTPError("401 Unauthorized", response=resp)
            force_refresh = True
            continue
        resp.raise_for_status()
        return resp.json()
    raise last_exc if last_exc else RuntimeError("graph_get exhausted retries")


def graph_get_binary(path, params=None, timeout=DEFAULT_TIMEOUT, token_getter=None):
    """GET a Graph resource and return the raw response bytes (not JSON).

    Same retry/401-refresh behavior as graph_get, but for binary endpoints like an
    attachment's `/$value` (the order-PDF bytes). Does not send Accept: json.
    """
    token_getter = token_getter or get_app_token
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    force_refresh = False
    last_exc = None
    for attempt in range(MAX_RETRIES):
        token = token_getter(force_refresh=force_refresh)
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=timeout,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            logger.warning("graph_get_binary_transient", url=url, attempt=attempt, error=str(exc))
            continue
        if resp.status_code == 401:
            logger.warning("graph_get_binary_401", url=url, attempt=attempt)
            last_exc = requests.HTTPError("401 Unauthorized", response=resp)
            force_refresh = True
            continue
        resp.raise_for_status()
        return resp.content
    raise last_exc if last_exc else RuntimeError("graph_get_binary exhausted retries")


def _graph_write(method, path, json_body=None, timeout=DEFAULT_TIMEOUT, token_getter=None):
    """Send a mutating Graph request (POST/PATCH/DELETE) and return parsed JSON or None.

    Same transient-retry + 401-refresh behavior as graph_get, for the subscription
    lifecycle (create/renew/delete). Returns the parsed JSON body when the response
    carries one (POST create → the subscription, PATCH renew → the updated sub) and
    None for empty bodies (DELETE → 204 No Content). `path` is relative to GRAPH_BASE
    or an absolute Graph URL.
    """
    token_getter = token_getter or get_app_token
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    force_refresh = False
    last_exc = None
    for attempt in range(MAX_RETRIES):
        token = token_getter(force_refresh=force_refresh)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        try:
            resp = requests.request(
                method, url, headers=headers, json=json_body, timeout=timeout
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            logger.warning("graph_write_transient", method=method, url=url, attempt=attempt, error=str(exc))
            continue
        if resp.status_code == 401:
            logger.warning("graph_write_401", method=method, url=url, attempt=attempt)
            last_exc = requests.HTTPError("401 Unauthorized", response=resp)
            force_refresh = True
            continue
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()
    raise last_exc if last_exc else RuntimeError("graph_write exhausted retries")


def graph_post(path, json_body, timeout=DEFAULT_TIMEOUT, token_getter=None):
    """POST a Graph resource (e.g. create a change-notification subscription)."""
    return _graph_write("POST", path, json_body=json_body, timeout=timeout, token_getter=token_getter)


def graph_patch(path, json_body, timeout=DEFAULT_TIMEOUT, token_getter=None):
    """PATCH a Graph resource (e.g. renew a subscription's expirationDateTime)."""
    return _graph_write("PATCH", path, json_body=json_body, timeout=timeout, token_getter=token_getter)


def graph_delete(path, timeout=DEFAULT_TIMEOUT, token_getter=None):
    """DELETE a Graph resource (e.g. tear down a stale subscription). Returns None."""
    return _graph_write("DELETE", path, json_body=None, timeout=timeout, token_getter=token_getter)
