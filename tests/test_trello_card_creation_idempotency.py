"""Tests for the idempotent-create path that prevents duplicate Trello cards
when a prior POST /1/cards got a 5xx false-negative from Trello.

Covers:
  - find_card_in_list_by_name lookup helper
  - create_trello_card_core idempotency_check behavior
  - create_trello_card_for_job skipping post-creation features on adoption
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.trello.api import find_card_in_list_by_name
from app.trello.card_creation import create_trello_card_core


# ---------------------------------------------------------------------------
# find_card_in_list_by_name
# ---------------------------------------------------------------------------

def _mock_get_response(json_payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_payload
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    return resp


def test_find_card_in_list_returns_first_exact_name_match():
    cards = [
        {"id": "a1", "name": "Other card"},
        {"id": "a2", "name": "500-615 Brinkman - Novel Flatiron SE Canopy"},
        {"id": "a3", "name": "Another unrelated"},
    ]
    with patch("app.trello.api.requests.get", return_value=_mock_get_response(cards)):
        result = find_card_in_list_by_name(
            "list-abc", "500-615 Brinkman - Novel Flatiron SE Canopy"
        )
    assert result is not None
    assert result["id"] == "a2"


def test_find_card_in_list_returns_none_when_no_match():
    cards = [{"id": "a1", "name": "Other card"}]
    with patch("app.trello.api.requests.get", return_value=_mock_get_response(cards)):
        result = find_card_in_list_by_name("list-abc", "Nope")
    assert result is None


def test_find_card_in_list_returns_none_for_empty_list():
    with patch("app.trello.api.requests.get", return_value=_mock_get_response([])):
        assert find_card_in_list_by_name("list-abc", "Anything") is None


def test_find_card_in_list_propagates_http_errors():
    with patch(
        "app.trello.api.requests.get",
        return_value=_mock_get_response({"message": "boom"}, status=500),
    ):
        with pytest.raises(requests.HTTPError):
            find_card_in_list_by_name("list-abc", "x")


# ---------------------------------------------------------------------------
# create_trello_card_core
# ---------------------------------------------------------------------------

def _mock_post_response(card_id="created-1", name="Title", status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"id": card_id, "name": name, "url": f"https://trello.com/c/{card_id}"}
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    return resp


def test_create_core_without_idempotency_check_posts_directly():
    with patch("app.trello.card_creation.requests.post", return_value=_mock_post_response()) as mock_post, \
         patch("app.trello.api.requests.get") as mock_get:
        result = create_trello_card_core(
            card_title="Title",
            card_description="Desc",
            list_id="list-abc",
            idempotency_check=False,
        )

    assert result["success"] is True
    assert result["adopted"] is False
    assert result["card_id"] == "created-1"
    mock_post.assert_called_once()
    mock_get.assert_not_called()


def test_create_core_with_idempotency_check_adopts_existing_card():
    existing = {
        "id": "existing-9",
        "name": "Title",
        "url": "https://trello.com/c/existing-9",
        "idList": "list-abc",
    }
    with patch(
        "app.trello.api.requests.get",
        return_value=_mock_get_response([{"id": "other", "name": "x"}, existing]),
    ) as mock_get, \
         patch("app.trello.card_creation.requests.post") as mock_post:
        result = create_trello_card_core(
            card_title="Title",
            card_description="Desc",
            list_id="list-abc",
            idempotency_check=True,
        )

    assert result["success"] is True
    assert result["adopted"] is True
    assert result["card_id"] == "existing-9"
    assert result["card_data"]["id"] == "existing-9"
    mock_get.assert_called_once()
    mock_post.assert_not_called()


def test_create_core_with_idempotency_check_posts_when_no_match():
    with patch(
        "app.trello.api.requests.get",
        return_value=_mock_get_response([{"id": "other", "name": "Different"}]),
    ) as mock_get, \
         patch(
        "app.trello.card_creation.requests.post",
        return_value=_mock_post_response(card_id="new-7", name="Title"),
    ) as mock_post:
        result = create_trello_card_core(
            card_title="Title",
            card_description="Desc",
            list_id="list-abc",
            idempotency_check=True,
        )

    assert result["success"] is True
    assert result["adopted"] is False
    assert result["card_id"] == "new-7"
    mock_get.assert_called_once()
    mock_post.assert_called_once()


def test_create_core_falls_through_to_post_when_scan_fails():
    """If the idempotency GET errors out we'd rather risk a duplicate than
    block the retry — verify the create path still runs."""
    with patch(
        "app.trello.api.requests.get",
        side_effect=requests.ConnectionError("network down"),
    ), \
         patch(
        "app.trello.card_creation.requests.post",
        return_value=_mock_post_response(card_id="fallback-3"),
    ) as mock_post:
        result = create_trello_card_core(
            card_title="Title",
            card_description="Desc",
            list_id="list-abc",
            idempotency_check=True,
        )

    assert result["success"] is True
    assert result["adopted"] is False
    assert result["card_id"] == "fallback-3"
    mock_post.assert_called_once()


# ---------------------------------------------------------------------------
# create_trello_card_for_job — adopted path skips post-creation features
# ---------------------------------------------------------------------------

def test_create_trello_card_for_job_skips_post_creation_when_adopted(app):
    """When the core adopts an existing card on retry, the wrapper must
    NOT re-run Fab Order / FC Drawing / notes / mirror — those side-effects
    aren't idempotent and likely already ran in the original attempt."""
    from app.brain.job_log.routes import create_trello_card_for_job
    from tests.conftest import make_release

    with app.app_context():
        job = make_release(500, "615", job_name="Brinkman", trello_card_id=None)

        adopted_card = {
            "id": "adopted-1",
            "name": "500-615 Brinkman Some desc",
            "url": "https://trello.com/c/adopted-1",
            "idList": "list-released",
        }

        with patch(
            "app.trello.api.get_list_by_name",
            return_value={"id": "list-released", "name": "Released"},
        ), \
             patch(
            "app.trello.card_creation.create_trello_card_core",
            return_value={
                "success": True,
                "adopted": True,
                "card_data": adopted_card,
                "card_id": "adopted-1",
            },
        ) as mock_core, \
             patch("app.trello.api.update_job_record_with_trello_data", return_value=True), \
             patch(
            "app.trello.card_creation.apply_card_post_creation_features",
        ) as mock_post_features:
            result = create_trello_card_for_job(
                job, {"Job #": 500, "Release #": "615"}, idempotency_check=True,
            )

        assert result["success"] is True
        assert result["adopted"] is True
        assert result["card_id"] == "adopted-1"
        mock_core.assert_called_once()
        assert mock_core.call_args.kwargs.get("idempotency_check") is True
        mock_post_features.assert_not_called()


def test_create_trello_card_for_job_runs_post_creation_on_fresh_create(app):
    """The non-adopted path must still run post-creation features."""
    from app.brain.job_log.routes import create_trello_card_for_job
    from tests.conftest import make_release

    with app.app_context():
        job = make_release(500, "616", job_name="Brinkman", trello_card_id=None)

        fresh_card = {
            "id": "fresh-1",
            "name": "500-616 Brinkman Some desc",
            "url": "https://trello.com/c/fresh-1",
            "idList": "list-released",
        }

        with patch(
            "app.trello.api.get_list_by_name",
            return_value={"id": "list-released", "name": "Released"},
        ), \
             patch(
            "app.trello.card_creation.create_trello_card_core",
            return_value={
                "success": True,
                "adopted": False,
                "card_data": fresh_card,
                "card_id": "fresh-1",
            },
        ), \
             patch("app.trello.api.update_job_record_with_trello_data", return_value=True), \
             patch(
            "app.trello.card_creation.apply_card_post_creation_features",
            return_value={"mirror_card_id": "mirror-1"},
        ) as mock_post_features:
            result = create_trello_card_for_job(
                job, {"Job #": 500, "Release #": "616"}, idempotency_check=False,
            )

        assert result["success"] is True
        assert result["adopted"] is False
        assert result["mirror_card_id"] == "mirror-1"
        mock_post_features.assert_called_once()
