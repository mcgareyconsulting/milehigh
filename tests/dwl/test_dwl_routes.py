"""
Tests for the Drafting Work Load routes (Flask endpoints).
These tests verify HTTP request/response handling, authentication, and route logic.
Shared fixtures (app, client, mock_admin_user, setup_auth, mock_submittal) live in conftest.py.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from app.models import Submittals, db


# ==============================================================================
# GET /drafting-work-load TESTS
# ==============================================================================

class TestGetDraftingWorkLoad:
    """Tests for GET /drafting-work-load endpoint."""

    @patch('app.brain.drafting_work_load.routes.DraftingWorkLoadService')
    def test_get_drafting_work_load_success(self, mock_service, client, mock_submittal):
        """Test successful retrieval of drafting work load."""
        mock_service.get_dwl_submittals.return_value = [mock_submittal]

        response = client.get('/brain/drafting-work-load')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'submittals' in data
        assert len(data['submittals']) == 1
        mock_service.get_dwl_submittals.assert_called_once_with(None, tab='open')

    @patch('app.brain.drafting_work_load.routes.DraftingWorkLoadService')
    def test_get_drafting_work_load_filters_by_status(self, mock_service, client):
        """Test that only Open and Draft submittals are returned (via service)."""
        mock_service.get_dwl_submittals.return_value = []

        response = client.get('/brain/drafting-work-load')

        assert response.status_code == 200
        mock_service.get_dwl_submittals.assert_called_once_with(None, tab='open')

    @patch('app.brain.drafting_work_load.routes.DraftingWorkLoadService')
    def test_get_drafting_work_load_error_handling(self, mock_service, client):
        """Test error handling when service raises."""
        mock_service.get_dwl_submittals.side_effect = Exception("Database error")

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
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    @patch('app.brain.drafting_work_load.routes.Submittals')
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
    
    @patch('app.brain.drafting_work_load.routes.Submittals')
    def test_update_due_date_invalid_format(self, mock_submittal_model, client, mock_submittal):
        """Test that invalid date format returns 400."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = mock_submittal

        response = client.put(
            '/brain/drafting-work-load/due-date',
            json={'submittal_id': 'test_123', 'due_date': '01/15/2024'},
            content_type='application/json'
        )

        assert response.status_code == 400


# ==============================================================================
# POST /drafting-work-load/step TESTS
# ==============================================================================

class TestStepSubmittalOrder:
    """Tests for POST /drafting-work-load/step endpoint."""

    @patch('app.brain.drafting_work_load.routes.db')
    @patch('app.brain.drafting_work_load.routes.Submittals')
    def test_step_success(self, mock_submittal_model, mock_db, client, mock_submittal):
        """Test successful step up returns 200 with swap details."""
        mock_submittal.order_number = 2.0
        mock_submittal.submittal_id = "test_submittal_123"
        mock_submittal.ball_in_court = "Drafter A"

        mock_neighbor = Mock(spec=Submittals)
        mock_neighbor.submittal_id = "neighbor_456"
        mock_neighbor.order_number = 1.0
        mock_neighbor.ball_in_court = "Drafter A"

        filter_by_chain = Mock()
        filter_by_chain.first.return_value = mock_submittal
        filter_by_chain.all.return_value = [mock_submittal, mock_neighbor]
        mock_submittal_model.query.filter_by.return_value = filter_by_chain

        response = client.post(
            '/brain/drafting-work-load/step',
            json={'submittal_id': 'test_submittal_123', 'direction': 'up'},
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'updates' in data

    def test_step_missing_submittal_id(self, client):
        """Test that missing submittal_id returns 400."""
        response = client.post(
            '/brain/drafting-work-load/step',
            json={'direction': 'up'},
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_step_invalid_direction(self, client):
        """Test that invalid direction returns 400."""
        response = client.post(
            '/brain/drafting-work-load/step',
            json={'submittal_id': 'test_123', 'direction': 'sideways'},
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('app.brain.drafting_work_load.routes.Submittals')
    def test_step_submittal_not_found(self, mock_submittal_model, client):
        """Test that non-existent submittal returns 404."""
        mock_submittal_model.query.filter_by.return_value.first.return_value = None

        response = client.post(
            '/brain/drafting-work-load/step',
            json={'submittal_id': 'nonexistent', 'direction': 'up'},
            content_type='application/json'
        )
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data

    @patch('app.brain.drafting_work_load.routes.Submittals')
    def test_step_at_top_returns_400(self, mock_submittal_model, client, mock_submittal):
        """Test that stepping up when already at top returns 400."""
        mock_submittal.order_number = 1.0
        mock_submittal.submittal_id = "test_submittal_123"
        mock_submittal.ball_in_court = "Drafter A"

        filter_by_chain = Mock()
        filter_by_chain.first.return_value = mock_submittal
        # Only one item in the group — no lower-order neighbor to swap with
        filter_by_chain.all.return_value = [mock_submittal]
        mock_submittal_model.query.filter_by.return_value = filter_by_chain

        response = client.post(
            '/brain/drafting-work-load/step',
            json={'submittal_id': 'test_submittal_123', 'direction': 'up'},
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


# ==============================================================================
# POST /drafting-work-load/resort TESTS
# ==============================================================================

class TestResortDrafterOrder:
    """Tests for POST /drafting-work-load/resort endpoint."""

    @patch('app.brain.drafting_work_load.routes.db')
    @patch('app.brain.drafting_work_load.routes.Submittals')
    def test_resort_success(self, mock_submittal_model, mock_db, client, mock_submittal):
        """Test successful resort returns 200 with update list."""
        mock_submittal.order_number = 3.0
        mock_submittal.submittal_id = "test_submittal_123"
        mock_submittal_model.query.filter_by.return_value.all.return_value = [mock_submittal]

        response = client.post(
            '/brain/drafting-work-load/resort',
            json={'ball_in_court': 'Drafter A'},
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'updates' in data

    def test_resort_missing_ball_in_court(self, client):
        """Test that missing ball_in_court returns 400."""
        response = client.post(
            '/brain/drafting-work-load/resort',
            json={},
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


# ==============================================================================
# GET /drafting-work-load/submittal-statuses TESTS
# ==============================================================================

class TestGetSubmittalStatuses:
    """Tests for GET /drafting-work-load/submittal-statuses endpoint."""

    def test_get_statuses_returns_list(self, client):
        """Test that GET returns 200 with a submittal_statuses list."""
        response = client.get('/brain/drafting-work-load/submittal-statuses')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'submittal_statuses' in data
        assert isinstance(data['submittal_statuses'], list)
