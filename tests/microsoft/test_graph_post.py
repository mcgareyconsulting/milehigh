"""Tests for graph_app_client.graph_post — the first outbound-write Graph call
in this codebase (everything else is graph_get). Uses an injected token_getter
so these don't need to mock the OAuth token-acquisition dance; that's already
covered by test_graph_delegated.py for the delegated flow this binds to.
"""
from unittest.mock import Mock, patch

import pytest
import requests

from app.microsoft import graph_app_client
from app.microsoft.graph_app_client import graph_post


def _token_getter(force_refresh=False):
    return "test-token"


def test_returns_none_on_empty_body_success():
    fake = Mock(status_code=202, content=b"")
    fake.raise_for_status = Mock()
    with patch.object(graph_app_client.requests, "post", return_value=fake) as post:
        result = graph_post("/me/sendMail", json_body={"message": {}}, token_getter=_token_getter)

    assert result is None
    post.assert_called_once()
    assert post.call_args.kwargs["json"] == {"message": {}}
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_returns_json_when_body_present():
    fake = Mock(status_code=201, content=b'{"id": "abc"}')
    fake.raise_for_status = Mock()
    fake.json.return_value = {"id": "abc"}
    with patch.object(graph_app_client.requests, "post", return_value=fake):
        result = graph_post("/some/resource", json_body={}, token_getter=_token_getter)

    assert result == {"id": "abc"}


def test_401_forces_refresh_then_retries():
    unauthorized = Mock(status_code=401, content=b"")
    ok = Mock(status_code=202, content=b"")
    ok.raise_for_status = Mock()

    calls = {"n": 0}

    def fake_token_getter(force_refresh=False):
        calls["n"] += 1
        calls["force_refresh"] = force_refresh
        return "refreshed-token" if force_refresh else "stale-token"

    with patch.object(graph_app_client.requests, "post", side_effect=[unauthorized, ok]) as post:
        result = graph_post("/me/sendMail", json_body={}, token_getter=fake_token_getter)

    assert result is None
    assert post.call_count == 2
    assert calls["force_refresh"] is True


def test_exhausts_retries_on_connection_error():
    with patch.object(graph_app_client.requests, "post", side_effect=requests.ConnectionError("down")):
        with pytest.raises(requests.ConnectionError):
            graph_post("/me/sendMail", json_body={}, token_getter=_token_getter)
