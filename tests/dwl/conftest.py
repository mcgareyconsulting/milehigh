"""
DWL-specific fixtures.

Shared fixtures (app, client, mock_admin_user) live in tests/conftest.py.
This file adds:
- setup_auth (autouse) — DWL tests run authenticated by default
- mock_submittal — DWL domain object
"""
import pytest
from unittest.mock import Mock, patch
from app.models import Submittals


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    """Automatically patch authentication for all tests in tests/dwl/."""
    with patch('app.auth.utils.get_current_user', return_value=mock_admin_user):
        yield


@pytest.fixture
def mock_submittal():
    """Create a mock submittal for testing."""
    submittal = Mock(spec=Submittals)
    submittal.submittal_id = "test_submittal_123"
    submittal.status = "Open"
    submittal.notes = None
    submittal.submittal_drafting_status = ""
    submittal.order_number = 1.0
    submittal.ball_in_court = "Drafter A"
    submittal.due_date = None
    submittal.last_updated = None

    def to_dict():
        return {
            'submittal_id': submittal.submittal_id,
            'status': submittal.status,
            'notes': submittal.notes,
            'submittal_drafting_status': submittal.submittal_drafting_status,
            'order_number': submittal.order_number,
            'ball_in_court': submittal.ball_in_court,
            'due_date': submittal.due_date.isoformat() if submittal.due_date else None,
        }

    submittal.to_dict = to_dict
    return submittal
