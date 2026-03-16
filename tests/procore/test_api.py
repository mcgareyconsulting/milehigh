"""
Unit tests for app/procore/api.py
"""
import pytest
import requests
from unittest.mock import patch, MagicMock, Mock

from app.procore.api import (
    SUBMITTAL_STATUS_ID_TO_NAME,
    VALID_SUBMITTAL_STATUS_IDS,
    ProcoreAPI,
)


class TestConstants:
    def test_status_id_to_name_contains_expected(self):
        assert 203239 in SUBMITTAL_STATUS_ID_TO_NAME
        assert SUBMITTAL_STATUS_ID_TO_NAME[203239] == "Closed"
        assert 203240 in SUBMITTAL_STATUS_ID_TO_NAME
        assert SUBMITTAL_STATUS_ID_TO_NAME[203240] == "Draft"
        assert 203238 in SUBMITTAL_STATUS_ID_TO_NAME
        assert SUBMITTAL_STATUS_ID_TO_NAME[203238] == "Open"

    def test_valid_status_ids_is_nonempty_set_of_ints(self):
        assert isinstance(VALID_SUBMITTAL_STATUS_IDS, set)
        assert len(VALID_SUBMITTAL_STATUS_IDS) > 0
        for sid in VALID_SUBMITTAL_STATUS_IDS:
            assert isinstance(sid, int)


@pytest.fixture
def api():
    """Return a ProcoreAPI instance with dummy credentials."""
    with patch("app.procore.api.get_access_token", return_value="fake-token"), \
         patch("app.procore.api.get_access_token_force_refresh", return_value="fake-token"):
        return ProcoreAPI(
            client_id="fake_id",
            client_secret="fake_secret",
            webhook_url="https://example.com/webhook",
        )


class TestUpdateSubmittalStatusValidation:
    def test_invalid_status_id_raises_value_error(self, api):
        with pytest.raises(ValueError, match="Invalid status_id"):
            api.update_submittal_status(project_id=1, submittal_id=1, status_id=99999)

    def test_valid_status_id_calls_patch(self, api):
        with patch.object(api, "_patch") as mock_patch:
            mock_patch.return_value = {}
            valid_id = next(iter(VALID_SUBMITTAL_STATUS_IDS))
            api.update_submittal_status(project_id=1, submittal_id=1, status_id=valid_id)
            mock_patch.assert_called_once()


class TestRequestRetry:
    def test_retries_on_connection_error_then_raises(self, api):
        with patch("app.procore.api.get_access_token", return_value="fake-token"), \
             patch("app.procore.api.time.sleep"), \
             patch.object(api.session, "request", side_effect=requests.exceptions.ConnectionError("conn refused")):
            with pytest.raises(requests.ConnectionError):
                api._request("GET", "/some/endpoint", max_retries=3, retry_delay=0.01)

    def test_succeeds_on_second_attempt(self, api):
        ok_response = Mock()
        ok_response.status_code = 200
        ok_response.text = '{"ok": true}'
        ok_response.json.return_value = {"ok": True}
        ok_response.raise_for_status = Mock()

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise requests.exceptions.ConnectionError("transient")
            return ok_response

        with patch("app.procore.api.get_access_token", return_value="fake-token"), \
             patch("app.procore.api.time.sleep"), \
             patch.object(api.session, "request", side_effect=side_effect):
            result = api._request("GET", "/some/endpoint", max_retries=3, retry_delay=0.01)

        assert result == {"ok": True}
        assert call_count["n"] == 2
