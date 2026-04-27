"""Tests for app/trello/__init__.py — POST /trello/webhook handler."""
from queue import Queue
from unittest.mock import patch, MagicMock

import pytest


_HANDLED = {
    "handled": True, "action_type": "updateCard",
    "card_id": "abc-123", "list_id": "list-1",
}
_UNHANDLED = {"handled": False, "action_type": "createList"}
_BODY = {"action": {"type": "updateCard"}}


@pytest.fixture
def trello_patches(request):
    """Patch the four module-level dependencies the webhook handler reads.

    Marker `event_payload` overrides parse_webhook_data's return; defaults
    to the handled fixture above. Marker `queue_size` provisions a fresh
    bounded queue (default 10).
    """
    parsed = getattr(request, "param", None) or _HANDLED
    queue = Queue(maxsize=getattr(request, "param_queue", 10))
    with patch("app.trello.parse_webhook_data", return_value=parsed), \
         patch("app.trello.executor") as mock_executor, \
         patch("app.trello.sync_lock_manager") as mock_lock, \
         patch("app.trello.trello_event_queue", queue):
        yield mock_executor, mock_lock, queue


def test_head_returns_200(client):
    assert client.head("/trello/webhook").status_code == 200


def test_unhandled_event_returns_200_without_submitting(client):
    with patch("app.trello.parse_webhook_data", return_value=_UNHANDLED), \
         patch("app.trello.executor") as mock_executor, \
         patch("app.trello.sync_lock_manager") as mock_lock:
        mock_lock.is_locked.return_value = False
        resp = client.post("/trello/webhook", json=_BODY)

    assert resp.status_code == 200
    mock_executor.submit.assert_not_called()


def test_lock_held_returns_202_and_enqueues(client, trello_patches):
    mock_executor, mock_lock, queue = trello_patches
    mock_lock.is_locked.return_value = True
    mock_lock.get_current_operation.return_value = "OneDrive-Snapshot"

    resp = client.post("/trello/webhook", json=_BODY)
    body = resp.get_json()

    assert resp.status_code == 202
    assert body["status"] == "queued"
    assert "OneDrive-Snapshot" in body["reason"]
    assert queue.qsize() == 1
    mock_executor.submit.assert_not_called()


def test_queue_full_when_lock_held_returns_429(client):
    full_queue = Queue(maxsize=1)
    full_queue.put_nowait({"already": "queued"})
    with patch("app.trello.parse_webhook_data", return_value=_HANDLED), \
         patch("app.trello.executor") as mock_executor, \
         patch("app.trello.sync_lock_manager") as mock_lock, \
         patch("app.trello.trello_event_queue", full_queue):
        mock_lock.is_locked.return_value = True
        mock_lock.get_current_operation.return_value = "OneDrive-Snapshot"
        resp = client.post("/trello/webhook", json=_BODY)

    assert resp.status_code == 429
    assert resp.get_json()["status"] == "overloaded"
    mock_executor.submit.assert_not_called()


def test_lock_free_submits_to_executor(client, trello_patches):
    mock_executor, mock_lock, _ = trello_patches
    mock_lock.is_locked.return_value = False
    future = MagicMock()
    mock_executor.submit.return_value = future

    resp = client.post("/trello/webhook", json=_BODY)

    assert resp.status_code == 200
    mock_executor.submit.assert_called_once()
    future.add_done_callback.assert_called_once()


def test_thread_stats_returns_tracker_snapshot(client):
    body = client.get("/trello/thread-stats").get_json()
    for key in ("total_started", "total_completed", "total_failed",
                "total_rejected", "active_count", "max_concurrent"):
        assert key in body
