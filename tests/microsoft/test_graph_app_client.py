"""Unit tests for the Graph app-only HTTP client.

Covers transient HTTP retry (504/429) — the failure mode that aborted Carmen
mail polls when Graph's front door timed out on fat inbox list queries.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.microsoft import graph_app_client as gac


def _resp(status, json_body=None, headers=None, reason=None):
    r = MagicMock()
    r.status_code = status
    r.reason = reason or {429: "Too Many Requests", 504: "Gateway Timeout"}.get(status, "Error")
    r.headers = headers or {}
    r.content = b"{}" if json_body is not None else b""
    if json_body is not None:
        r.json.return_value = json_body
    else:
        r.json.side_effect = ValueError("no json")

    def raise_for_status():
        if status >= 400:
            raise requests.HTTPError(f"{status} {r.reason}", response=r)

    r.raise_for_status.side_effect = raise_for_status
    return r


@pytest.fixture(autouse=True)
def _fast_sleep():
    with patch.object(gac.time, "sleep") as sleep:
        yield sleep


@pytest.fixture
def token():
    with patch.object(gac, "get_app_token", return_value="tok"):
        yield


def test_graph_get_retries_504_then_succeeds(token, _fast_sleep):
    ok = _resp(200, {"value": []})
    with patch.object(
        gac.requests, "get", side_effect=[_resp(504), _resp(504), ok]
    ) as get:
        data = gac.graph_get("/users/x/messages")

    assert data == {"value": []}
    assert get.call_count == 3
    assert _fast_sleep.call_count == 2


def test_graph_get_raises_after_exhausted_504s(token, _fast_sleep):
    with patch.object(gac.requests, "get", return_value=_resp(504)):
        with pytest.raises(requests.HTTPError) as ei:
            gac.graph_get("/users/x/messages")

    assert ei.value.response.status_code == 504
    # Final attempt does not sleep — only intermediate retries do.
    assert _fast_sleep.call_count == gac.MAX_RETRIES - 1


def test_graph_get_honors_retry_after_on_429(token, _fast_sleep):
    ok = _resp(200, {"ok": True})
    with patch.object(
        gac.requests, "get", side_effect=[_resp(429, headers={"Retry-After": "7"}), ok]
    ):
        assert gac.graph_get("/users/x/messages") == {"ok": True}

    _fast_sleep.assert_called_once_with(7)


def test_graph_get_does_not_retry_404(token, _fast_sleep):
    with patch.object(gac.requests, "get", return_value=_resp(404, reason="Not Found")) as get:
        with pytest.raises(requests.HTTPError):
            gac.graph_get("/users/x/messages/missing")

    assert get.call_count == 1
    _fast_sleep.assert_not_called()


def test_retry_delay_caps_retry_after():
    resp = MagicMock()
    resp.headers = {"Retry-After": "999"}
    assert gac._retry_delay_seconds(resp, 0) == gac.MAX_RETRY_DELAY_SECONDS
