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


# ==============================================================================
# PUT /drafting-work-load/rel  +  GET /drafting-work-load/rel/next TESTS
# ==============================================================================

DRR_TYPE = "Drafting Release Review"


def _seed_submittal(submittal_id, type_=DRR_TYPE, status="Open", rel=None):
    """Commit a real Submittals row so the rel endpoints' DB queries see it."""
    s = Submittals(
        submittal_id=str(submittal_id),
        procore_project_id="1",
        project_number="100",
        type=type_,
        status=status,
        rel=rel,
        rel_assigned_at=datetime.utcnow() if rel is not None else None,
    )
    db.session.add(s)
    db.session.commit()
    return s


def _seed_active_release(job, release, **extra):
    from app.models import Releases
    fields = {"is_active": True, "is_archived": False}
    fields.update(extra)
    r = Releases(job=int(job), release=str(release), job_name="Test Job", **fields)
    db.session.add(r)
    db.session.commit()
    return r


class TestUpdateSubmittalRel:
    """Tests for PUT /drafting-work-load/rel endpoint (real DB rows)."""

    def test_assign_rel_happy_path(self, client):
        _seed_submittal("rel-1")
        response = client.put(
            '/brain/drafting-work-load/rel',
            json={'submittal_id': 'rel-1', 'rel': 200},
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['rel'] == 200
        assert Submittals.query.filter_by(submittal_id='rel-1').first().rel == 200

    def test_assign_rel_non_drr_rejected(self, client):
        _seed_submittal("rel-2", type_="Submittal for GC Approval")
        response = client.put(
            '/brain/drafting-work-load/rel',
            json={'submittal_id': 'rel-2', 'rel': 200},
        )
        assert response.status_code == 400
        assert json.loads(response.data)['code'] == 'type'

    @pytest.mark.parametrize("bad", [50, 1000])
    def test_assign_rel_out_of_range(self, client, bad):
        _seed_submittal("rel-3")
        response = client.put(
            '/brain/drafting-work-load/rel',
            json={'submittal_id': 'rel-3', 'rel': bad},
        )
        assert response.status_code == 400
        assert json.loads(response.data)['code'] == 'range'

    def test_assign_rel_collision_active_release(self, client):
        _seed_active_release(777, 200)  # active release 200 on another job
        _seed_submittal("rel-4")
        response = client.put(
            '/brain/drafting-work-load/rel',
            json={'submittal_id': 'rel-4', 'rel': 200},
        )
        assert response.status_code == 409
        assert json.loads(response.data)['code'] == 'collision'

    def test_assign_rel_collision_other_pending_drr(self, client):
        _seed_submittal("rel-holder", rel=200)  # pending DRR already holds 200
        _seed_submittal("rel-5")
        response = client.put(
            '/brain/drafting-work-load/rel',
            json={'submittal_id': 'rel-5', 'rel': 200},
        )
        assert response.status_code == 409
        assert json.loads(response.data)['code'] == 'collision'

    def test_assign_rel_reassign_self_allowed(self, client):
        _seed_submittal("rel-6", rel=200)
        # same number
        same = client.put('/brain/drafting-work-load/rel',
                          json={'submittal_id': 'rel-6', 'rel': 200})
        assert same.status_code == 200
        # different number
        diff = client.put('/brain/drafting-work-load/rel',
                          json={'submittal_id': 'rel-6', 'rel': 201})
        assert diff.status_code == 200
        assert Submittals.query.filter_by(submittal_id='rel-6').first().rel == 201

    def test_assign_rel_archived_release_does_not_block(self, client):
        _seed_active_release(777, 200, is_archived=True)
        _seed_submittal("rel-7")
        response = client.put('/brain/drafting-work-load/rel',
                              json={'submittal_id': 'rel-7', 'rel': 200})
        assert response.status_code == 200

    def test_assign_rel_missing_rel(self, client):
        _seed_submittal("rel-8")
        response = client.put('/brain/drafting-work-load/rel',
                              json={'submittal_id': 'rel-8'})
        assert response.status_code == 400

    def test_assign_rel_not_found(self, client):
        response = client.put('/brain/drafting-work-load/rel',
                              json={'submittal_id': 'nope', 'rel': 200})
        assert response.status_code == 404

    def test_assign_rel_writes_audit_event(self, client):
        from app.models import SubmittalEvents
        _seed_submittal("rel-9")
        client.put('/brain/drafting-work-load/rel',
                   json={'submittal_id': 'rel-9', 'rel': 200})
        events = SubmittalEvents.query.filter_by(submittal_id='rel-9', action='updated').all()
        assert any(e.payload and e.payload.get('rel') == {'old': None, 'new': 200} for e in events)

    def test_assign_rel_forbidden_for_non_drafter(self, client, mock_non_admin_user):
        _seed_submittal("rel-10")
        with patch('app.auth.utils.get_current_user', return_value=mock_non_admin_user):
            response = client.put('/brain/drafting-work-load/rel',
                                  json={'submittal_id': 'rel-10', 'rel': 200})
        assert response.status_code == 403


class TestGetNextRel:
    """Tests for GET /drafting-work-load/rel/next endpoint."""

    def test_next_rel_default(self, client):
        response = client.get('/brain/drafting-work-load/rel/next')
        assert response.status_code == 200
        assert json.loads(response.data)['next_rel'] == 101

    def test_next_rel_is_max_in_use_plus_one(self, client):
        _seed_active_release(777, 300)
        response = client.get('/brain/drafting-work-load/rel/next')
        # Highest in use is 300 -> suggestion is 301.
        assert json.loads(response.data)['next_rel'] == 301

    def test_next_rel_excludes_self(self, client):
        # 's1' (pending) holds the high-water mark 300; an active release sits at
        # 250. Excluding 's1' drops the max to 250 -> 251; including it -> 301.
        _seed_submittal("s1", rel=300, status="Open")
        _seed_active_release(777, 250)
        with_self = client.get('/brain/drafting-work-load/rel/next?submittal_id=s1')
        assert json.loads(with_self.data)['next_rel'] == 251
        without = client.get('/brain/drafting-work-load/rel/next')
        assert json.loads(without.data)['next_rel'] == 301
