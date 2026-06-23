"""Microsoft Graph delegated client (device-code flow) for the BB mailbox.

No admin consent required: bb@mhmw.com self-consents once via the device-code
flow (scripts/link_bb_mailbox.py) — user consent, not admin consent, and no
redirect URI. The resulting refresh token is stored in MicrosoftDelegatedToken;
the poller/connector exchange it for access tokens on demand. Used when org
policy blocks app-only application permissions.

Device-code is a public-client flow, so no client secret is used here — the app
registration just needs "Allow public client flows" = Yes plus delegated
Mail.ReadWrite / Mail.Send / offline_access.
"""
import threading
import time
from datetime import datetime, timedelta

import requests

from app.config import Config as cfg
from app.logging_config import get_logger
from app.microsoft.graph_app_client import graph_get as _graph_get
from app.models import MicrosoftDelegatedToken, db

logger = get_logger(__name__)

# Delegated scopes bb@mhmw.com consents to. offline_access is required to get a
# refresh token; Mail.ReadWrite/Mail.Send cover read + draft + send.
DELEGATED_SCOPES = "offline_access Mail.ReadWrite Mail.Send"
TOKEN_REFRESH_BUFFER_SECONDS = 120
DEFAULT_TIMEOUT = 30

_token_lock = threading.Lock()


class MicrosoftDelegatedAuthError(RuntimeError):
    """Raised when the BB mailbox is not linked or its refresh token is dead."""


def _authority_base():
    return f"https://login.microsoftonline.com/{cfg.AZURE_TENANT_ID}/oauth2/v2.0"


def _account_email():
    return (cfg.BB_MAILBOX or "").lower()


def _persist_token(token, account_email):
    expires_at = datetime.utcnow() + timedelta(seconds=int(token.get("expires_in", 3600)))
    row = MicrosoftDelegatedToken.get_for_account(account_email)
    if row is None:
        row = MicrosoftDelegatedToken(account_email=account_email)
        db.session.add(row)
    row.access_token = token["access_token"]
    # Refresh tokens rotate on use — always store the latest one Graph returns.
    if token.get("refresh_token"):
        row.refresh_token = token["refresh_token"]
    row.token_expires_at = expires_at
    row.scopes = token.get("scope", DELEGATED_SCOPES)
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return row


# --- One-time interactive linking (run via scripts/link_bb_mailbox.py) ---

def request_device_code():
    """Start the device-code flow. Returns the devicecode response dict."""
    resp = requests.post(
        f"{_authority_base()}/devicecode",
        data={"client_id": cfg.AZURE_CLIENT_ID, "scope": DELEGATED_SCOPES},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def poll_for_token(device_code, interval, expires_in):
    """Poll the token endpoint until the user completes sign-in. Returns token dict."""
    deadline = time.time() + expires_in
    wait = max(int(interval), 1)
    while time.time() < deadline:
        time.sleep(wait)
        resp = requests.post(
            f"{_authority_base()}/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": cfg.AZURE_CLIENT_ID,
                "device_code": device_code,
            },
            timeout=DEFAULT_TIMEOUT,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code == 200:
            return data
        error = data.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            wait += 5
            continue
        raise RuntimeError(
            f"Device-code sign-in failed: {error}: {data.get('error_description', '')}"
        )
    raise RuntimeError("Device-code sign-in timed out before completion.")


def link_mailbox(printer=print):
    """Interactive one-time device-code link for the BB mailbox. Returns the row."""
    flow = request_device_code()
    printer("\n" + flow.get(
        "message",
        f"Go to {flow['verification_uri']} and enter code {flow['user_code']}",
    ))
    printer(f"\nSign in as: {_account_email()}\nWaiting for sign-in to complete...")
    token = poll_for_token(
        flow["device_code"],
        flow.get("interval", 5),
        int(flow.get("expires_in", 900)),
    )
    row = _persist_token(token, _account_email())
    printer(f"\n✓ Linked {row.account_email}. Scopes: {row.scopes}")
    return row


# --- Token use (poller / connector) ---

def _refresh(row):
    resp = requests.post(
        f"{_authority_base()}/token",
        data={
            "grant_type": "refresh_token",
            "client_id": cfg.AZURE_CLIENT_ID,
            "refresh_token": row.refresh_token,
            "scope": DELEGATED_SCOPES,
        },
        timeout=DEFAULT_TIMEOUT,
    )
    if resp.status_code != 200:
        data = resp.json() if resp.content else {}
        raise MicrosoftDelegatedAuthError(
            f"Refresh failed ({resp.status_code}): {data.get('error')}: "
            f"{data.get('error_description', '')}. Re-run scripts/link_bb_mailbox.py."
        )
    return _persist_token(resp.json(), row.account_email)


def _is_expiring(row):
    return (
        row.token_expires_at is None
        or row.token_expires_at <= datetime.utcnow() + timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS)
    )


def get_delegated_token(force_refresh=False):
    """Return a valid delegated access token for the BB mailbox, refreshing as needed.

    Raises MicrosoftDelegatedAuthError if the mailbox has never been linked or
    the refresh token is no longer valid (re-run scripts/link_bb_mailbox.py).
    """
    with _token_lock:
        row = MicrosoftDelegatedToken.get_for_account(_account_email())
        if row is None or not row.refresh_token:
            raise MicrosoftDelegatedAuthError(
                f"Mailbox {_account_email()} is not linked. Run scripts/link_bb_mailbox.py."
            )
        if force_refresh or _is_expiring(row):
            row = _refresh(row)
        return row.access_token


def graph_get(path, params=None, timeout=DEFAULT_TIMEOUT):
    """graph_get bound to the BB delegated identity (drop-in for the connector)."""
    return _graph_get(path, params=params, timeout=timeout, token_getter=get_delegated_token)
