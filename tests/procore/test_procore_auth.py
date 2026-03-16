"""
Unit tests for app/procore/procore_auth.py — focusing on _is_expiring().
"""
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.procore.procore_auth import _is_expiring, TOKEN_REFRESH_BUFFER_SECONDS


def _token_expiring_in(seconds: float) -> Mock:
    """Return a mock ProcoreToken whose expires_at is `seconds` from now."""
    token = Mock()
    token.expires_at = datetime.utcnow() + timedelta(seconds=seconds)
    return token


class TestIsExpiring:
    def test_close_to_expiry_returns_true(self):
        token = _token_expiring_in(30)
        assert _is_expiring(token) is True

    def test_far_from_expiry_returns_false(self):
        token = _token_expiring_in(300)
        assert _is_expiring(token) is False

    def test_at_exact_buffer_returns_true(self):
        # expires_at == utcnow() + buffer → condition is `<=` so True
        token = _token_expiring_in(TOKEN_REFRESH_BUFFER_SECONDS)
        assert _is_expiring(token) is True

    def test_none_expires_at_returns_true(self):
        token = Mock()
        token.expires_at = None
        assert _is_expiring(token) is True
