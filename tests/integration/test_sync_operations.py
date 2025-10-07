"""
Integration tests for sync operations.

These tests use the database and mock external APIs to test
the complete sync workflows.
"""
import pytest
from datetime import datetime, date
from unittest.mock import patch, Mock

from app.models import Job, SyncOperation, SyncLog, SyncStatus
from app.sync import (
    create_sync_operation,
    update_sync_operation,
    sync_from_trello,
    rectify_db_on_trello_move
)


class TestSyncOperationManagement:
    """Test sync operation creation and management."""
    
    @pytest.mark.integration
    def test_create_sync_operation(self, db_session):
        """Test creating a sync operation record."""
        sync_op = create_sync_operation(
            operation_type="test_operation",
            source_system="test",
            source_id="test_123"
        )
        
        assert sync_op.operation_id is not None
        assert len(sync_op.operation_id) == 8  # UUID truncated to 8 chars
        assert sync_op.operation_type == "test_operation"
        assert sync_op.status == SyncStatus.PENDING
        assert sync_op.source_system == "test"
        assert sync_op.source_id == "test_123"
        assert sync_op.started_at is not None
        
        # Verify it was saved to database
        saved_op = SyncOperation.query.filter_by(operation_id=sync_op.operation_id).first()
        assert saved_op is not None
        assert saved_op.operation_type == "test_operation"
    
    @pytest.mark.integration
    def test_update_sync_operation(self, db_session, sample_sync_operation):
        """Test updating a sync operation record."""
        updated_op = update_sync_operation(
            sample_sync_operation.operation_id,
            status=SyncStatus.COMPLETED,
            records_processed=5,
            records_updated=3
        )
        
        assert updated_op.status == SyncStatus.COMPLETED
        assert updated_op.records_processed == 5
        assert updated_op.records_updated == 3
        
        # Verify it was updated in database
        saved_op = SyncOperation.query.filter_by(operation_id=sample_sync_operation.operation_id).first()
        assert saved_op.status == SyncStatus.COMPLETED
        assert saved_op.records_processed == 5
        assert saved_op.records_updated == 3


class TestRectifyDbOnTrelloMove:
    """Test database rectification on Trello card moves."""
    
    @pytest.mark.integration
    def test_rectify_paint_complete_move(self, db_session, sample_job):
        """Test rectifying job status for Paint complete move."""
        # Reset job status
        sample_job.fitup_comp = "O"
        sample_job.welded = "O"
        sample_job.paint_comp = ""
        sample_job.ship = ""
        db_session.commit()
        
        rectify_db_on_trello_move(sample_job, "Paint complete", "test_op")
        
        assert sample_job.fitup_comp == "X"
        assert sample_job.welded == "X"
        assert sample_job.paint_comp == "X"
        assert sample_job.ship == "O"
    
    @pytest.mark.integration
    def test_rectify_fitup_complete_move(self, db_session, sample_job):
        """Test rectifying job status for Fit Up Complete move."""
        # Reset job status
        sample_job.fitup_comp = "O"
        sample_job.welded = "X"
        sample_job.paint_comp = "X"
        sample_job.ship = "X"
        db_session.commit()
        
        rectify_db_on_trello_move(sample_job, "Fit Up Complete.", "test_op")
        
        assert sample_job.fitup_comp == "X"
        assert sample_job.welded == "O"
        assert sample_job.paint_comp == ""
        assert sample_job.ship == ""
    
    @pytest.mark.integration
    def test_rectify_shipping_completed_move(self, db_session, sample_job):
        """Test rectifying job status for Shipping completed move."""
        # Reset job status
        sample_job.fitup_comp = "O"
        sample_job.welded = "O"
        sample_job.paint_comp = "O"
        sample_job.ship = "O"
        db_session.commit()
        
        rectify_db_on_trello_move(sample_job, "Shipping completed", "test_op")
        
        assert sample_job.fitup_comp == "X"
        assert sample_job.welded == "X"
        assert sample_job.paint_comp == "X"
        assert sample_job.ship == "X"


class TestSyncFromTrello:
    """Test sync from Trello webhook functionality."""
    
    @pytest.mark.integration
    def test_sync_from_trello_card_moved(self, db_session, sample_job, mock_trello_api):
        """Test sync from Trello when card is moved."""
        event_info = {
            "handled": True,
            "event": "card_moved",
            "card_id": sample_job.trello_card_id,
            "time": "2023-01-21T16:00:00.000Z"
        }
        
        # Update the mock to return our test card
        mock_trello_api["get_card"].return_value = {
            "id": sample_job.trello_card_id,
            "name": sample_job.trello_card_name,
            "desc": "Updated description",
            "idList": "new_list_123",
            "due": "2023-02-02T18:00:00.000Z"
        }
        mock_trello_api["get_list_name"].return_value = "Paint complete"
        
        # Set initial job state
        sample_job.last_updated_at = datetime(2023, 1, 20, 10, 0, 0)
        sample_job.source_of_update = "System"
        sample_job.fitup_comp = "O"
        sample_job.welded = "O"
        sample_job.paint_comp = ""
        sample_job.ship = ""
        db_session.commit()
        
        sync_from_trello(event_info)
        
        # Refresh job from database
        db_session.refresh(sample_job)
        
        # Check that job was updated
        assert sample_job.source_of_update == "Trello"
        assert sample_job.trello_list_name == "Paint complete"
        assert sample_job.fitup_comp == "X"
        assert sample_job.welded == "X"
        assert sample_job.paint_comp == "X"
        assert sample_job.ship == "O"
        
        # Check that sync operation was created
        sync_ops = SyncOperation.query.filter_by(source_id=sample_job.trello_card_id).all()
        assert len(sync_ops) > 0
        assert sync_ops[0].status == SyncStatus.COMPLETED
    
    @pytest.mark.integration
    def test_sync_from_trello_no_update_needed(self, db_session, sample_job, mock_trello_api):
        """Test sync from Trello when no update is needed."""
        event_info = {
            "handled": True,
            "event": "card_updated",
            "card_id": sample_job.trello_card_id,
            "time": "2023-01-19T16:00:00.000Z"  # Older than job's last update
        }
        
        # Set job to be newer than event
        sample_job.last_updated_at = datetime(2023, 1, 20, 10, 0, 0)
        sample_job.source_of_update = "System"
        db_session.commit()
        
        sync_from_trello(event_info)
        
        # Check that sync operation was created but skipped
        sync_ops = SyncOperation.query.filter_by(source_id=sample_job.trello_card_id).all()
        assert len(sync_ops) > 0
        assert sync_ops[0].status == SyncStatus.SKIPPED
    
    @pytest.mark.integration
    def test_sync_from_trello_card_not_found(self, db_session, mock_trello_api):
        """Test sync from Trello when card is not found."""
        event_info = {
            "handled": True,
            "event": "card_updated",
            "card_id": "nonexistent_card",
            "time": "2023-01-21T16:00:00.000Z"
        }
        
        # Mock API to return None (card not found)
        mock_trello_api["get_card"].return_value = None
        
        sync_from_trello(event_info)
        
        # Check that sync operation was created but failed
        sync_ops = SyncOperation.query.filter_by(source_id="nonexistent_card").all()
        assert len(sync_ops) > 0
        assert sync_ops[0].status == SyncStatus.FAILED
        assert sync_ops[0].error_type == "CardNotFound"
    
    @pytest.mark.integration
    def test_sync_from_trello_unhandled_event(self, db_session):
        """Test sync from Trello with unhandled event."""
        event_info = {
            "handled": False,
            "event": "unhandled"
        }
        
        sync_from_trello(event_info)
        
        # Should return early without creating sync operation
        sync_ops = SyncOperation.query.all()
        assert len(sync_ops) == 0
    
    @pytest.mark.integration
    def test_sync_from_trello_duplicate_trello_update(self, db_session, sample_job, mock_trello_api):
        """Test sync from Trello with duplicate Trello update."""
        event_info = {
            "handled": True,
            "event": "card_updated",
            "card_id": sample_job.trello_card_id,
            "time": "2023-01-20T10:00:00.000Z"  # Same time as job's last update
        }
        
        # Set job to be from Trello with same timestamp
        sample_job.last_updated_at = datetime(2023, 1, 20, 10, 0, 0)
        sample_job.source_of_update = "Trello"
        db_session.commit()
        
        sync_from_trello(event_info)
        
        # Check that sync operation was created but skipped
        sync_ops = SyncOperation.query.filter_by(source_id=sample_job.trello_card_id).all()
        assert len(sync_ops) > 0
        assert sync_ops[0].status == SyncStatus.SKIPPED
