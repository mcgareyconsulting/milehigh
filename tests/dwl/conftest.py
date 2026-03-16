"""
Shared fixtures for the DWL test suite.
Extracted from test_dwl_routes.py so all test files in tests/dwl/ can use them.
"""
import pytest
from unittest.mock import Mock, patch
from app import create_app
from app.models import Submittals, db


@pytest.fixture
def app():
    """Create Flask application for testing. Uses in-memory SQLite only."""
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"

    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    assert "sandbox" not in uri.lower() and "render.com" not in uri, (
        "Tests must not use sandbox/production DB. Set TESTING=1 before create_app (see tests/conftest.py)."
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for authentication."""
    user = Mock()
    user.id = 1
    user.username = "test_admin"
    user.is_admin = True
    user.is_active = True
    return user


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    """Automatically patch authentication for all tests in tests/dwl/."""
    with patch('app.auth.utils.get_current_user', return_value=mock_admin_user):
        yield


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


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
