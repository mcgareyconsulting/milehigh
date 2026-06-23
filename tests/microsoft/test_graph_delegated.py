"""Tests for the delegated (device-code) token getter.

Network is mocked; the DB is the real in-memory SQLite from tests/conftest.py.
Covers the not-linked error, the cached-token fast path, and refresh + rotation.
"""
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from app.microsoft import graph_delegated
from app.microsoft.graph_delegated import MicrosoftDelegatedAuthError, get_delegated_token
from app.models import MicrosoftDelegatedToken, db


def _seed(email="bb@mhmw.com", expires_in_min=60, refresh="r0", access="a0"):
    row = MicrosoftDelegatedToken(
        account_email=email,
        access_token=access,
        refresh_token=refresh,
        token_expires_at=datetime.utcnow() + timedelta(minutes=expires_in_min),
        scopes=graph_delegated.DELEGATED_SCOPES,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_raises_when_not_linked(app):
    with pytest.raises(MicrosoftDelegatedAuthError):
        get_delegated_token()


def test_raises_when_no_refresh_token(app):
    _seed(refresh=None)
    with pytest.raises(MicrosoftDelegatedAuthError):
        get_delegated_token()


def test_returns_cached_when_valid(app):
    _seed(expires_in_min=60, access="a0")
    assert get_delegated_token() == "a0"


def test_refreshes_when_expiring_and_rotates_refresh_token(app):
    _seed(expires_in_min=0, refresh="r0", access="a0")  # already within the buffer

    fake = Mock(status_code=200, content=b"{}")
    fake.json.return_value = {
        "access_token": "a1", "refresh_token": "r1",
        "expires_in": 3600, "scope": graph_delegated.DELEGATED_SCOPES,
    }
    with patch.object(graph_delegated.requests, "post", return_value=fake) as post:
        token = get_delegated_token()

    assert token == "a1"
    post.assert_called_once()
    assert post.call_args.kwargs["data"]["grant_type"] == "refresh_token"

    row = MicrosoftDelegatedToken.get_for_account("bb@mhmw.com")
    assert row.access_token == "a1"
    assert row.refresh_token == "r1"  # rotated


def test_refresh_failure_raises_auth_error(app):
    _seed(expires_in_min=0, refresh="dead")
    fake = Mock(status_code=400, content=b'{"error":"invalid_grant"}')
    fake.json.return_value = {"error": "invalid_grant", "error_description": "expired"}
    with patch.object(graph_delegated.requests, "post", return_value=fake):
        with pytest.raises(MicrosoftDelegatedAuthError):
            get_delegated_token()
