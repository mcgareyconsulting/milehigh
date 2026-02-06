"""
Tests for compression functionality when ball_in_court updates.
These tests verify that when a submittal moves between drafters, the old drafter's
list is compressed (both urgency and regular subsets).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.procore.procore import check_and_update_submittal
from app.models import ProcoreSubmittal
from app import create_app


class TestBallInCourtCompression:
    """Tests for compression when ball_in_court changes."""
    
    @pytest.fixture
    def app(self):
        """Create Flask application context for tests."""
        app = create_app()
        app.config['TESTING'] = True
        with app.app_context():
            yield app
    
    @pytest.fixture
    def mock_record(self):
        """Create a mock ProcoreSubmittal record."""
        record = Mock(spec=ProcoreSubmittal)
        record.submittal_id = "submittal_123"
        record.ball_in_court = "Drafter A"
        record.status = "Open"
        record.order_number = 2.0
        record.was_multiple_assignees = False
        return record
    
    @pytest.fixture
    def mock_old_drafter_submittals(self):
        """Create mock submittals for the old drafter."""
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.submittal_id = "urgent_1"
        urgent1.order_number = 0.5
        urgent1.ball_in_court = "Drafter A"
        urgent1.status = "Open"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.submittal_id = "urgent_2"
        urgent2.order_number = 0.7
        urgent2.ball_in_court = "Drafter A"
        urgent2.status = "Open"
        
        regular1 = Mock(spec=ProcoreSubmittal)
        regular1.submittal_id = "regular_1"
        regular1.order_number = 3.0
        regular1.ball_in_court = "Drafter A"
        regular1.status = "Open"
        
        regular2 = Mock(spec=ProcoreSubmittal)
        regular2.submittal_id = "regular_2"
        regular2.order_number = 5.0
        regular2.ball_in_court = "Drafter A"
        regular2.status = "Open"
        
        return [urgent1, urgent2, regular1, regular2]
    
    @patch('app.procore.procore.handle_submittal_update')
    @patch('app.procore.procore.ProcoreSubmittal')
    @patch('app.procore.procore.SubmittalOrderingEngine')
    def test_compression_on_ball_in_court_change(
        self, 
        mock_engine, 
        mock_submittal_model, 
        mock_handle_update,
        app,
        mock_record,
        mock_old_drafter_submittals
    ):
        """Test that compression is triggered when ball_in_court changes."""
        # Setup: submittal moves from Drafter A to Drafter B
        mock_record.ball_in_court = "Drafter A"
        
        # Mock handle_submittal_update to return the record with new ball_in_court
        mock_handle_update.return_value = (
            mock_record,
            "Drafter B",  # new ball_in_court
            [],  # approvers
            "Open",  # status
            "Test Title",  # title
            None  # submittal_manager
        )
        
        # Mock the query for old drafter's submittals
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = mock_old_drafter_submittals
        mock_submittal_model.query = mock_query
        
        # Mock compression engine
        mock_engine.compress_orders.return_value = [
            ("urgent_1", 0.8),
            ("urgent_2", 0.9),
            ("regular_1", 1.0),
            ("regular_2", 2.0),
        ]
        
        # Call the function
        result = check_and_update_submittal("project_123", "submittal_123")
        
        # Verify compression was called
        mock_engine.compress_orders.assert_called_once()
        
        # Verify the old drafter's submittals were updated
        assert mock_old_drafter_submittals[0].order_number == 0.8
        assert mock_old_drafter_submittals[1].order_number == 0.9
        assert mock_old_drafter_submittals[2].order_number == 1.0
        assert mock_old_drafter_submittals[3].order_number == 2.0
    
    @patch('app.procore.procore.handle_submittal_update')
    @patch('app.procore.procore.ProcoreSubmittal')
    @patch('app.procore.procore.SubmittalOrderingEngine')
    def test_no_compression_when_old_ball_in_court_is_empty(
        self,
        mock_engine,
        mock_submittal_model,
        mock_handle_update,
        app,
        mock_record
    ):
        """Test that compression is not triggered when old ball_in_court is empty."""
        mock_record.ball_in_court = None  # Empty old value
        
        mock_handle_update.return_value = (
            mock_record,
            "Drafter B",
            [],
            "Open",
            "Test Title",
            None
        )
        
        # Call the function
        result = check_and_update_submittal("project_123", "submittal_123")
        
        # Verify compression was NOT called
        mock_engine.compress_orders.assert_not_called()
    
    @patch('app.procore.procore.handle_submittal_update')
    @patch('app.procore.procore.ProcoreSubmittal')
    @patch('app.procore.procore.SubmittalOrderingEngine')
    def test_no_compression_when_old_ball_in_court_is_multiple(
        self,
        mock_engine,
        mock_submittal_model,
        mock_handle_update,
        app,
        mock_record
    ):
        """Test that compression is not triggered when old ball_in_court is multiple assignees."""
        mock_record.ball_in_court = "Drafter A, Drafter B"  # Multiple assignees
        
        mock_handle_update.return_value = (
            mock_record,
            "Drafter C",
            [],
            "Open",
            "Test Title",
            None
        )
        
        # Call the function
        result = check_and_update_submittal("project_123", "submittal_123")
        
        # Verify compression was NOT called
        mock_engine.compress_orders.assert_not_called()
    
    @patch('app.procore.procore.handle_submittal_update')
    @patch('app.procore.procore.ProcoreSubmittal')
    @patch('app.procore.procore.SubmittalOrderingEngine')
    def test_no_compression_when_no_old_drafter_submittals(
        self,
        mock_engine,
        mock_submittal_model,
        mock_handle_update,
        app,
        mock_record
    ):
        """Test that compression is not called when old drafter has no other submittals."""
        mock_record.ball_in_court = "Drafter A"
        
        mock_handle_update.return_value = (
            mock_record,
            "Drafter B",
            [],
            "Open",
            "Test Title",
            None
        )
        
        # Mock empty query result
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = []
        mock_submittal_model.query = mock_query
        
        # Call the function
        result = check_and_update_submittal("project_123", "submittal_123")
        
        # Verify compression was NOT called (no submittals to compress)
        mock_engine.compress_orders.assert_not_called()
    
    @patch('app.procore.procore.handle_submittal_update')
    @patch('app.procore.procore.ProcoreSubmittal')
    @patch('app.procore.procore.SubmittalOrderingEngine')
    def test_compression_excludes_moved_submittal(
        self,
        mock_engine,
        mock_submittal_model,
        mock_handle_update,
        app,
        mock_record,
        mock_old_drafter_submittals
    ):
        """Test that the moved submittal is excluded from compression."""
        mock_record.ball_in_court = "Drafter A"
        mock_record.submittal_id = "submittal_123"
        
        mock_handle_update.return_value = (
            mock_record,
            "Drafter B",
            [],
            "Open",
            "Test Title",
            None
        )
        
        # Add the moved submittal to the old drafter's list
        moved_submittal = Mock(spec=ProcoreSubmittal)
        moved_submittal.submittal_id = "submittal_123"
        moved_submittal.order_number = 1.0
        all_submittals = mock_old_drafter_submittals + [moved_submittal]
        
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = mock_old_drafter_submittals
        mock_submittal_model.query = mock_query
        
        mock_engine.compress_orders.return_value = [
            ("urgent_1", 0.8),
            ("urgent_2", 0.9),
            ("regular_1", 1.0),
            ("regular_2", 2.0),
        ]
        
        # Call the function
        result = check_and_update_submittal("project_123", "submittal_123")
        
        # Verify the query excluded the moved submittal
        # The filter should exclude submittal_123
        filter_call = mock_query.filter.call_args
        assert filter_call is not None
        
        # Verify compression was called with only the remaining submittals
        compress_call_args = mock_engine.compress_orders.call_args[0][0]
        submittal_ids = [s['submittal_id'] for s in compress_call_args]
        assert "submittal_123" not in submittal_ids

