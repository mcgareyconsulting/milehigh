"""Tests for app/procore/__init__.py — POST /procore/webhook handler.

Helpers (`is_duplicate_webhook`, `parse_ball_in_court_from_submittal`) are
covered in tests/procore/test_helpers.py.
"""
from unittest.mock import patch, MagicMock

from app.models import Submittals, db


def _payload(resource_id=42, project_id=99, reason="update", resource_type="submittals"):
    return {
        "resource_id": resource_id,
        "project_id": project_id,
        "reason": reason,
        "resource_type": resource_type,
    }


def test_head_returns_200(client):
    assert client.head("/procore/webhook").status_code == 200


def test_post_missing_resource_id_returns_ignored(client):
    resp = client.post("/procore/webhook", json={"project_id": 99, "reason": "update"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"


def test_post_missing_project_id_returns_ignored(client):
    resp = client.post("/procore/webhook", json={"resource_id": 42, "reason": "update"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"


def test_post_invalid_resource_id_returns_ignored(client):
    resp = client.post("/procore/webhook", json={
        "resource_id": "not-a-number", "project_id": 99, "reason": "update",
    })
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"


def test_duplicate_webhook_returns_deduplicated(client):
    with patch("app.procore.is_duplicate_webhook", return_value=True), \
         patch("app.procore.create_submittal_from_webhook") as mock_create, \
         patch("app.procore.check_and_update_submittal") as mock_update:
        resp = client.post("/procore/webhook", json=_payload(reason="update"))

    assert resp.get_json()["status"] == "deduplicated"
    mock_create.assert_not_called()
    mock_update.assert_not_called()


def _record_mock(**kwargs):
    record = MagicMock()
    record.title = kwargs.get("title", "Submittal 042")
    record.project_name = kwargs.get("project_name", "Project Phoenix")
    record.submittal_manager = kwargs.get("submittal_manager")
    return record


def test_create_event_calls_create_submittal_from_webhook(client):
    with patch("app.procore.is_duplicate_webhook", return_value=False), \
         patch(
             "app.procore.create_submittal_from_webhook",
             return_value=(True, _record_mock(), None),
         ) as mock_create:
        client.post("/procore/webhook", json=_payload(reason="create"))

    kwargs = mock_create.call_args.kwargs
    assert kwargs["source"] == "Procore"
    assert kwargs["webhook_payload"]["reason"] == "create"


def test_update_event_with_existing_submittal_calls_check_and_update(app, client):
    with app.app_context():
        db.session.add(Submittals(
            submittal_id="42",
            procore_project_id=99,
            project_name="Project Phoenix",
            title="Submittal 042",
            status="Open",
            ball_in_court="Drafter A",
        ))
        db.session.commit()

    with patch("app.procore.is_duplicate_webhook", return_value=False), \
         patch("app.procore.create_submittal_from_webhook") as mock_create, \
         patch(
             "app.procore.check_and_update_submittal",
             return_value=(False, False, False, False, _record_mock(), "Drafter A", "Open"),
         ) as mock_update:
        client.post("/procore/webhook", json=_payload(reason="update"))

    mock_update.assert_called_once()
    mock_create.assert_not_called()


def test_update_event_missing_submittal_falls_back_to_create(client):
    """Race condition: update arrives before create — handler falls back to create."""
    record = _record_mock()
    with patch("app.procore.is_duplicate_webhook", return_value=False), \
         patch(
             "app.procore.create_submittal_from_webhook",
             return_value=(True, record, None),
         ) as mock_create, \
         patch(
             "app.procore.check_and_update_submittal",
             return_value=(False, False, False, False, record, None, None),
         ):
        client.post("/procore/webhook", json=_payload(reason="update"))

    mock_create.assert_called_once()


def test_unknown_event_type_is_ignored(client):
    with patch("app.procore.is_duplicate_webhook", return_value=False), \
         patch("app.procore.create_submittal_from_webhook") as mock_create, \
         patch("app.procore.check_and_update_submittal") as mock_update:
        client.post("/procore/webhook", json=_payload(reason="delete"))

    mock_create.assert_not_called()
    mock_update.assert_not_called()
