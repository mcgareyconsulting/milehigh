"""
Unit tests for sync operations.
"""
import pytest
from datetime import datetime, date
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from app.sync import (
    create_sync_operation,
    update_sync_operation,
    safe_log_sync_event,
    compare_timestamps,
    as_date,
    determine_trello_list_from_db,
    is_formula_cell,
    rectify_db_on_trello_move
)
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus


@pytest.mark.unit
@pytest.mark.sync
class TestSyncOperationManagement:
    """Test sync operation creation and management."""
    
    def test_create_sync_operation(self, app_context):
        """Test creating a sync operation."""
        op = create_sync_operation(
            operation_type="test_operation",
            source_system="test_system",
            source_id="test_id"
        )
        
        assert op.operation_type == "test_operation"
        assert op.source_system == "test_system"
        assert op.source_id == "test_id"
        assert op.status == SyncStatus.PENDING
        assert op.operation_id is not None
        assert len(op.operation_id) == 8  # UUID first 8 characters
        
        # Verify it was saved to database
        saved_op = SyncOperation.query.filter_by(operation_id=op.operation_id).first()
        assert saved_op is not None
        assert saved_op.operation_type == "test_operation"
    
    def test_update_sync_operation(self, app_context, sample_sync_operation):
        """Test updating a sync operation."""
        db.session.add(sample_sync_operation)
        db.session.commit()
        
        # Update the operation
        updated_op = update_sync_operation(
            sample_sync_operation.operation_id,
            status=SyncStatus.COMPLETED,
            records_updated=5,
            duration_seconds=1.5
        )
        
        assert updated_op.status == SyncStatus.COMPLETED
        assert updated_op.records_updated == 5
        assert updated_op.duration_seconds == 1.5
        
        # Verify changes were saved
        saved_op = SyncOperation.query.filter_by(operation_id=sample_sync_operation.operation_id).first()
        assert saved_op.status == SyncStatus.COMPLETED
        assert saved_op.records_updated == 5
    
    def test_update_nonexistent_sync_operation(self, app_context):
        """Test updating a non-existent sync operation."""
        result = update_sync_operation("nonexistent_id", status=SyncStatus.FAILED)
        assert result is None


@pytest.mark.unit
@pytest.mark.sync
class TestSafeLogSyncEvent:
    """Test safe sync event logging."""
    
    def test_safe_log_sync_event_success(self, app_context):
        """Test successful sync event logging."""
        operation_id = "test_op_123"
        
        safe_log_sync_event(
            operation_id,
            "INFO",
            "Test message",
            job_id=1,
            trello_card_id="card123",
            excel_identifier="123-456",
            test_data="test_value"
        )
        
        # Verify log was created
        log = SyncLog.query.filter_by(operation_id=operation_id).first()
        assert log is not None
        assert log.level == "INFO"
        assert log.message == "Test message"
        assert log.job_id == 1
        assert log.trello_card_id == "card123"
        assert log.excel_identifier == "123-456"
        assert log.data["test_data"] == "test_value"
    
    def test_safe_log_sync_event_with_pandas_data(self, app_context):
        """Test logging with pandas data that needs JSON serialization."""
        operation_id = "test_op_456"
        
        # Create data with pandas types
        import pandas as pd
        import numpy as np
        
        safe_log_sync_event(
            operation_id,
            "INFO",
            "Test pandas data",
            pandas_timestamp=pd.Timestamp("2024-01-15"),
            numpy_int=np.int64(123),
            numpy_float=np.float64(45.6),
            pandas_na=pd.NA
        )
        
        # Verify log was created and data was properly serialized
        log = SyncLog.query.filter_by(operation_id=operation_id).first()
        assert log is not None
        assert isinstance(log.data["pandas_timestamp"], str)
        assert log.data["numpy_int"] == 123
        assert log.data["numpy_float"] == 45.6
        assert log.data["pandas_na"] is None
    
    @patch('app.sync.logger')
    def test_safe_log_sync_event_error_handling(self, mock_logger, app_context):
        """Test error handling in sync event logging."""
        operation_id = "test_op_error"
        
        # Mock database session to raise an error
        with patch('app.sync.db.session.commit', side_effect=Exception("DB Error")):
            safe_log_sync_event(operation_id, "INFO", "Test message")
        
        # Should have logged a warning about the failure
        mock_logger.warning.assert_called_once()


@pytest.mark.unit
@pytest.mark.sync
class TestCompareTimestamps:
    """Test timestamp comparison logic."""
    
    def test_compare_timestamps_newer(self):
        """Test when event time is newer than source time."""
        event_time = datetime(2024, 1, 15, 12, 0, 0)
        source_time = datetime(2024, 1, 15, 11, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "newer"
    
    def test_compare_timestamps_older(self):
        """Test when event time is older than source time."""
        event_time = datetime(2024, 1, 15, 11, 0, 0)
        source_time = datetime(2024, 1, 15, 12, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "older"
    
    def test_compare_timestamps_equal(self):
        """Test when event time equals source time."""
        event_time = datetime(2024, 1, 15, 12, 0, 0)
        source_time = datetime(2024, 1, 15, 12, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "older"  # Equal is treated as older
    
    def test_compare_timestamps_no_source_time(self):
        """Test when source time is None."""
        event_time = datetime(2024, 1, 15, 12, 0, 0)
        source_time = None
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "newer"
    
    def test_compare_timestamps_no_event_time(self):
        """Test when event time is None."""
        event_time = None
        source_time = datetime(2024, 1, 15, 12, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result is None


@pytest.mark.unit
@pytest.mark.sync
class TestAsDate:
    """Test date conversion utility."""
    
    def test_as_date_with_date(self):
        """Test converting date object."""
        test_date = date(2024, 1, 15)
        result = as_date(test_date)
        assert result == test_date
    
    def test_as_date_with_datetime(self):
        """Test converting datetime object."""
        test_datetime = datetime(2024, 1, 15, 12, 30, 0)
        result = as_date(test_datetime)
        assert result == date(2024, 1, 15)
    
    def test_as_date_with_pandas_timestamp(self):
        """Test converting pandas Timestamp."""
        import pandas as pd
        test_timestamp = pd.Timestamp("2024-01-15")
        result = as_date(test_timestamp)
        assert result == date(2024, 1, 15)
    
    def test_as_date_with_string(self):
        """Test converting date string."""
        test_string = "2024-01-15"
        result = as_date(test_string)
        assert result == date(2024, 1, 15)
    
    def test_as_date_with_none(self):
        """Test converting None."""
        result = as_date(None)
        assert result is None
    
    def test_as_date_with_pandas_na(self):
        """Test converting pandas NA."""
        import pandas as pd
        result = as_date(pd.NA)
        assert result is None
    
    def test_as_date_with_invalid_string(self):
        """Test converting invalid date string."""
        result = as_date("invalid-date")
        assert result is None


@pytest.mark.unit
@pytest.mark.sync
class TestDetermineTrelloListFromDb:
    """Test Trello list determination from database status."""
    
    def test_paint_complete_status(self, sample_job):
        """Test Paint complete status determination."""
        sample_job.fitup_comp = "X"
        sample_job.welded = "X"
        sample_job.paint_comp = "X"
        sample_job.ship = "O"
        
        result = determine_trello_list_from_db(sample_job)
        assert result == "Paint complete"
    
    def test_paint_complete_status_with_t(self, sample_job):
        """Test Paint complete status with ship = T."""
        sample_job.fitup_comp = "X"
        sample_job.welded = "X"
        sample_job.paint_comp = "X"
        sample_job.ship = "T"
        
        result = determine_trello_list_from_db(sample_job)
        assert result == "Paint complete"
    
    def test_fit_up_complete_status(self, sample_job):
        """Test Fit Up Complete status determination."""
        sample_job.fitup_comp = "X"
        sample_job.welded = "O"
        sample_job.paint_comp = None
        sample_job.ship = None
        
        result = determine_trello_list_from_db(sample_job)
        assert result == "Fit Up Complete."
    
    def test_shipping_completed_status(self, sample_job):
        """Test Shipping completed status determination."""
        sample_job.fitup_comp = "X"
        sample_job.welded = "X"
        sample_job.paint_comp = "X"
        sample_job.ship = "X"
        
        result = determine_trello_list_from_db(sample_job)
        assert result == "Shipping completed"
    
    def test_no_matching_status(self, sample_job):
        """Test when no status matches."""
        sample_job.fitup_comp = "O"
        sample_job.welded = ""
        sample_job.paint_comp = ""
        sample_job.ship = ""
        
        result = determine_trello_list_from_db(sample_job)
        assert result is None


@pytest.mark.unit
@pytest.mark.sync
class TestIsFormulaCell:
    """Test formula cell detection."""
    
    def test_is_formula_cell_with_formula_flag(self):
        """Test formula detection with formulaTF flag."""
        row = {
            "start_install_formula": "=TODAY()+7",
            "start_install_formulaTF": True
        }
        
        result = is_formula_cell(row)
        assert result is True
    
    def test_is_formula_cell_with_formula_string(self):
        """Test formula detection with formula string."""
        row = {
            "start_install_formula": "=TODAY()+7",
            "start_install_formulaTF": False
        }
        
        result = is_formula_cell(row)
        assert result is True
    
    def test_is_formula_cell_no_formula(self):
        """Test formula detection with no formula."""
        row = {
            "start_install_formula": "2024-01-15",
            "start_install_formulaTF": False
        }
        
        result = is_formula_cell(row)
        assert result is False
    
    def test_is_formula_cell_empty_formula(self):
        """Test formula detection with empty formula."""
        row = {
            "start_install_formula": "",
            "start_install_formulaTF": False
        }
        
        result = is_formula_cell(row)
        assert result is False


@pytest.mark.unit
@pytest.mark.sync
class TestRectifyDbOnTrelloMove:
    """Test database rectification on Trello card moves."""
    
    def test_rectify_paint_complete_move(self, sample_job):
        """Test rectifying move to Paint complete."""
        rectify_db_on_trello_move(sample_job, "Paint complete", "test_op")
        
        assert sample_job.fitup_comp == "X"
        assert sample_job.welded == "X"
        assert sample_job.paint_comp == "X"
        assert sample_job.ship == "O"
    
    def test_rectify_fit_up_complete_move(self, sample_job):
        """Test rectifying move to Fit Up Complete."""
        rectify_db_on_trello_move(sample_job, "Fit Up Complete.", "test_op")
        
        assert sample_job.fitup_comp == "X"
        assert sample_job.welded == "O"
        assert sample_job.paint_comp == ""
        assert sample_job.ship == ""
    
    def test_rectify_shipping_completed_move(self, sample_job):
        """Test rectifying move to Shipping completed."""
        rectify_db_on_trello_move(sample_job, "Shipping completed", "test_op")
        
        assert sample_job.fitup_comp == "X"
        assert sample_job.welded == "X"
        assert sample_job.paint_comp == "X"
        assert sample_job.ship == "X"
    
    def test_rectify_unknown_list_move(self, sample_job):
        """Test rectifying move to unknown list (no changes)."""
        original_fitup = sample_job.fitup_comp
        original_welded = sample_job.welded
        original_paint = sample_job.paint_comp
        original_ship = sample_job.ship
        
        rectify_db_on_trello_move(sample_job, "Unknown List", "test_op")
        
        # Should remain unchanged
        assert sample_job.fitup_comp == original_fitup
        assert sample_job.welded == original_welded
        assert sample_job.paint_comp == original_paint
        assert sample_job.ship == original_ship
