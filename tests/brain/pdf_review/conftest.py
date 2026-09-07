"""Hermetic Anthropic credentials for the pdf_review suite.

Both `chat.ask` and `service._call_anthropic` check `Config.ANTHROPIC_API_KEY` and bail
out BEFORE the transport — chat returns its `configured: False` stub, review raises. So a
test that mocks `_post` / `requests.post` silently never reaches its mock on a machine with
no key, and every assertion about the request shape passes vacuously or dies on a `None`
`call_args`. That is exactly how these tests passed locally (dev `.env` has a key) and
failed in CI (no key).

The fixture pins a fake key so the suite behaves the same in both places. Tests covering
the no-key path patch it back to None themselves, which still nests correctly.
"""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _fake_anthropic_key():
    # Patched on Config itself: `chat` and `service` both alias the same class object,
    # so one patch covers both. Never a real key — nothing here may reach the network.
    with patch("app.config.Config.ANTHROPIC_API_KEY", "test-key-not-real"):
        yield
