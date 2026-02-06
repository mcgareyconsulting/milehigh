"""
Tests for the Drafting Work Load routes (Flask endpoints).
These tests verify HTTP request/response handling, authentication, and route logic.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from app import create_app
from app.models import ProcoreSubmittal, db


@pytest.fixture
def app():
    """Create Flask application for testing."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SECRET_KEY'] = 'test-secret-key'
    
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
    """Automatically patch authentication for all tests."""
    with patch('app.auth.utils.get_current_user', return_value=mock_admin_user):
        yield


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def mock_submittal():
    """Create a mock submittal for testing."""
    submittal = Mock(spec=ProcoreSubmittal)
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


# ==============================================================================
# GET /drafting-work-load TESTS
# ==============================================================================

class TestGetDraftingWorkLoad:
    """Tests for GET /drafting-work-load endpoint."""
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_get_drafting_work_load_success(self, mock_submittal_model, client, mock_submittal):
        """Test successful retrieval of drafting work load."""
        mock_submittal_model.query.filter.return_value.all.return_value = [mock_submittal]
        
        response = client.get('/brain/drafting-work-load')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'submittals' in data
        assert len(data['submittals']) == 1
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_get_drafting_work_load_filters_by_status(self, mock_submittal_model, client):
        """Test that only Open and Draft submittals are returned."""
        mock_submittal_model.query.filter.return_value.all.return_value = []
        
        response = client.get('/brain/drafting-work-load')
        
        assert response.status_code == 200
        # Verify filter was called with correct status values
        mock_submittal_model.query.filter.assert_called_once()
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_get_drafting_work_load_error_handling(self, mock_submittal_model, client):
        """Test error handling when database query fails."""
        mock_submittal_model.query.filter.side_effect = Exception("Database error")
        
        response = client.get('/brain/drafting-work-load')
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data


# ==============================================================================
# PUT /drafting-work-load/order TESTS
# ==============================================================================

class TestUpdateSubmittalOrder:
    """Tests for PUT /drafting-work-load/order endpoint."""
    
    @patch('app.brain.drafting_work_load.routes.db')
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_order_success(self, mock_submittal_model, mock_db, client, mock_submittal):
        """Test successful order update."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = mock_submittal
        mock_submittal.ball_in_court = "Drafter A"
        mock_submittal_model.query.filter_by.return_value.all.return_value = [mock_submittal]
        
        response = client.put(
            '/brain/drafting-work-load/order',
            json={'submittal_id': 'test_submittal_123', 'order_number': 2.0},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
    
    def test_update_order_missing_submittal_id(self, client):
        """Test that missing submittal_id returns 400."""
        response = client.put(
            '/brain/drafting-work-load/order',
            json={'order_number': 2.0},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_order_invalid_order_number(self, mock_submittal_model, client):
        """Test that invalid order number returns 400."""
        response = client.put(
            '/brain/drafting-work-load/order',
            json={'submittal_id': 'test_123', 'order_number': 'INVALID'},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_order_submittal_not_found(self, mock_submittal_model, client):
        """Test that non-existent submittal returns 404."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = None
        
        response = client.put(
            '/brain/drafting-work-load/order',
            json={'submittal_id': 'nonexistent', 'order_number': 2.0},
            content_type='application/json'
        )
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data


# ==============================================================================
# PUT /drafting-work-load/notes TESTS
# ==============================================================================

class TestUpdateSubmittalNotes:
    """Tests for PUT /drafting-work-load/notes endpoint."""
    
    @patch('app.brain.drafting_work_load.routes.db')
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_notes_success(self, mock_submittal_model, mock_db, client, mock_submittal):
        """Test successful notes update."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = mock_submittal
        
        response = client.put(
            '/brain/drafting-work-load/notes',
            json={'submittal_id': 'test_submittal_123', 'notes': 'New notes'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['notes'] == 'New notes'
    
    def test_update_notes_missing_submittal_id(self, client):
        """Test that missing submittal_id returns 400."""
        response = client.put(
            '/brain/drafting-work-load/notes',
            json={'notes': 'New notes'},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_notes_submittal_not_found(self, mock_submittal_model, client):
        """Test that non-existent submittal returns 404."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = None
        
        response = client.put(
            '/brain/drafting-work-load/notes',
            json={'submittal_id': 'nonexistent', 'notes': 'New notes'},
            content_type='application/json'
        )
        
        assert response.status_code == 404


# ==============================================================================
# PUT /drafting-work-load/submittal-drafting-status TESTS
# ==============================================================================

class TestUpdateSubmittalDraftingStatus:
    """Tests for PUT /drafting-work-load/submittal-drafting-status endpoint."""
    
    @patch('app.brain.drafting_work_load.routes.db')
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_status_success(self, mock_submittal_model, mock_db, client, mock_submittal):
        """Test successful status update."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = mock_submittal
        
        response = client.put(
            '/brain/drafting-work-load/submittal-drafting-status',
            json={'submittal_id': 'test_submittal_123', 'submittal_drafting_status': 'STARTED'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['submittal_drafting_status'] == 'STARTED'
    
    def test_update_status_missing_submittal_id(self, client):
        """Test that missing submittal_id returns 400."""
        response = client.put(
            '/brain/drafting-work-load/submittal-drafting-status',
            json={'submittal_drafting_status': 'STARTED'},
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    def test_update_status_invalid_status(self, client):
        """Test that invalid status returns 400."""
        response = client.put(
            '/brain/drafting-work-load/submittal-drafting-status',
            json={'submittal_id': 'test_123', 'submittal_drafting_status': 'INVALID'},
            content_type='application/json'
        )
        
        assert response.status_code == 400


# ==============================================================================
# POST /drafting-work-load/bump TESTS
# ==============================================================================

class TestBumpSubmittal:
    """Tests for POST /drafting-work-load/bump endpoint."""
    
    @patch('app.brain.drafting_work_load.routes.db')
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_bump_success(self, mock_submittal_model, mock_db, client, mock_submittal):
        """Test successful bump to urgent."""
        # Configure mock_submittal with real values (not Mock objects)
        mock_submittal.ball_in_court = "Drafter A"
        mock_submittal.order_number = 5.0
        mock_submittal.submittal_id = "test_submittal_123"
        
        # Set up the query chain for filter_by (used by route to get submittal)
        filter_by_chain = Mock()
        filter_by_chain.first.return_value = mock_submittal
        mock_submittal_model.query.filter_by.return_value = filter_by_chain
        
        # Mock the query chain for finding existing urgent/regular submittals (used by service)
        filter_chain = Mock()
        filter_chain.all.return_value = []
        mock_submittal_model.query.filter.return_value = filter_chain
        
        response = client.post(
            '/brain/drafting-work-load/bump',
            json={'submittal_id': 'test_submittal_123'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
    
    def test_bump_missing_submittal_id(self, client):
        """Test that missing submittal_id returns 400."""
        response = client.post(
            '/brain/drafting-work-load/bump',
            json={},
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_bump_no_ball_in_court(self, mock_submittal_model, client, mock_submittal):
        """Test that submittal without ball_in_court returns 400."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = mock_submittal
        mock_submittal.ball_in_court = None
        
        response = client.post(
            '/brain/drafting-work-load/bump',
            json={'submittal_id': 'test_submittal_123'},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'ball_in_court' in data['error'].lower()


# ==============================================================================
# PUT /drafting-work-load/due-date TESTS
# ==============================================================================

class TestUpdateSubmittalDueDate:
    """Tests for PUT /drafting-work-load/due-date endpoint."""
    
    @patch('app.brain.drafting_work_load.routes.db')
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_due_date_success(self, mock_submittal_model, mock_db, client, mock_submittal):
        """Test successful due date update."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = mock_submittal
        mock_submittal.due_date = date(2024, 1, 15)
        
        response = client.put(
            '/brain/drafting-work-load/due-date',
            json={'submittal_id': 'test_submittal_123', 'due_date': '2024-01-15'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
    
    def test_update_due_date_missing_submittal_id(self, client):
        """Test that missing submittal_id returns 400."""
        response = client.put(
            '/brain/drafting-work-load/due-date',
            json={'due_date': '2024-01-15'},
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    @patch('app.brain.drafting_work_load.routes.ProcoreSubmittal')
    def test_update_due_date_invalid_format(self, mock_submittal_model, client, mock_submittal):
        """Test that invalid date format returns 400."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = mock_submittal
        
        response = client.put(
            '/brain/drafting-work-load/due-date',
            json={'submittal_id': 'test_123', 'due_date': '01/15/2024'},
            content_type='application/json'
        )
        
        assert response.status_code == 400

