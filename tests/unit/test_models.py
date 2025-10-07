"""
Unit tests for database models.

These tests focus on model methods, validation, and basic functionality
without complex database interactions.
"""
import pytest
from datetime import datetime, date

from app.models import Job, SyncOperation, SyncLog, SyncStatus


class TestSyncOperation:
    """Test SyncOperation model functionality."""
    
    @pytest.mark.unit
    def test_sync_operation_creation(self):
        """Test creating a SyncOperation instance."""
        sync_op = SyncOperation(
            operation_id="test_op_123",
            operation_type="test_operation",
            status=SyncStatus.PENDING,
            source_system="test",
            source_id="test_source_123"
        )
        
        assert sync_op.operation_id == "test_op_123"
        assert sync_op.operation_type == "test_operation"
        assert sync_op.status == SyncStatus.PENDING
        assert sync_op.source_system == "test"
        assert sync_op.source_id == "test_source_123"
        assert sync_op.records_processed == 0
        assert sync_op.records_updated == 0
        assert sync_op.records_created == 0
        assert sync_op.records_failed == 0
    
    @pytest.mark.unit
    def test_sync_operation_to_dict(self):
        """Test converting SyncOperation to dictionary."""
        sync_op = SyncOperation(
            operation_id="test_op_123",
            operation_type="test_operation",
            status=SyncStatus.COMPLETED,
            source_system="test",
            source_id="test_source_123",
            records_processed=5,
            records_updated=3,
            records_created=1,
            records_failed=1
        )
        sync_op.started_at = datetime(2023, 1, 20, 15, 0, 0)
        sync_op.completed_at = datetime(2023, 1, 20, 15, 5, 0)
        sync_op.duration_seconds = 300.0
        
        result = sync_op.to_dict()
        
        assert result["operation_id"] == "test_op_123"
        assert result["operation_type"] == "test_operation"
        assert result["status"] == "completed"
        assert result["source_system"] == "test"
        assert result["source_id"] == "test_source_123"
        assert result["records_processed"] == 5
        assert result["records_updated"] == 3
        assert result["records_created"] == 1
        assert result["records_failed"] == 1
        assert result["duration_seconds"] == 300.0
        assert "2023-01-20T15:00:00" in result["started_at"]
        assert "2023-01-20T15:05:00" in result["completed_at"]
    
    @pytest.mark.unit
    def test_sync_operation_repr(self):
        """Test SyncOperation string representation."""
        sync_op = SyncOperation(
            operation_id="test_op_123",
            operation_type="test_operation",
            status=SyncStatus.IN_PROGRESS
        )
        
        result = repr(sync_op)
        assert "test_op_123" in result
        assert "test_operation" in result
        assert "in_progress" in result


class TestSyncLog:
    """Test SyncLog model functionality."""
    
    @pytest.mark.unit
    def test_sync_log_creation(self):
        """Test creating a SyncLog instance."""
        sync_log = SyncLog(
            operation_id="test_op_123",
            level="INFO",
            message="Test message",
            job_id=456,
            trello_card_id="card_123",
            excel_identifier="123-V456",
            data={"key": "value"}
        )
        
        assert sync_log.operation_id == "test_op_123"
        assert sync_log.level == "INFO"
        assert sync_log.message == "Test message"
        assert sync_log.job_id == 456
        assert sync_log.trello_card_id == "card_123"
        assert sync_log.excel_identifier == "123-V456"
        assert sync_log.data == {"key": "value"}
    
    @pytest.mark.unit
    def test_sync_log_repr(self):
        """Test SyncLog string representation."""
        sync_log = SyncLog(
            operation_id="test_op_123",
            level="ERROR",
            message="This is a very long test message that should be truncated in the repr"
        )
        
        result = repr(sync_log)
        assert "test_op_123" in result
        assert "ERROR" in result
        assert "This is a very long test message that should be" in result
        assert "..." in result


class TestJob:
    """Test Job model functionality."""
    
    @pytest.mark.unit
    def test_job_creation(self):
        """Test creating a Job instance."""
        job = Job(
            job=123,
            release="V456",
            job_name="Test Job",
            description="Test Description",
            fab_hrs=10.5,
            install_hrs=5.0,
            paint_color="Blue",
            pm="PM1",
            by="BY1",
            released=date(2023, 1, 15),
            fab_order=1.0,
            cut_start="X",
            fitup_comp="X",
            welded="O",
            paint_comp="",
            ship="",
            start_install=date(2023, 2, 1),
            start_install_formula="",
            start_install_formulaTF=False,
            comp_eta=date(2023, 2, 15),
            job_comp="",
            invoiced="",
            notes="Test notes"
        )
        
        assert job.job == 123
        assert job.release == "V456"
        assert job.job_name == "Test Job"
        assert job.description == "Test Description"
        assert job.fab_hrs == 10.5
        assert job.install_hrs == 5.0
        assert job.paint_color == "Blue"
        assert job.pm == "PM1"
        assert job.by == "BY1"
        assert job.released == date(2023, 1, 15)
        assert job.fab_order == 1.0
        assert job.cut_start == "X"
        assert job.fitup_comp == "X"
        assert job.welded == "O"
        assert job.paint_comp == ""
        assert job.ship == ""
        assert job.start_install == date(2023, 2, 1)
        assert job.start_install_formula == ""
        assert job.start_install_formulaTF is False
        assert job.comp_eta == date(2023, 2, 15)
        assert job.job_comp == ""
        assert job.invoiced == ""
        assert job.notes == "Test notes"
    
    @pytest.mark.unit
    def test_job_with_trello_fields(self):
        """Test Job instance with Trello fields."""
        job = Job(
            job=123,
            release="V456",
            job_name="Test Job",
            trello_card_id="card_123",
            trello_card_name="Trello Card Name",
            trello_list_id="list_123",
            trello_list_name="In Progress",
            trello_card_description="Card description",
            trello_card_date=date(2023, 2, 1),
            last_updated_at=datetime(2023, 1, 20, 10, 0, 0),
            source_of_update="Trello"
        )
        
        assert job.trello_card_id == "card_123"
        assert job.trello_card_name == "Trello Card Name"
        assert job.trello_list_id == "list_123"
        assert job.trello_list_name == "In Progress"
        assert job.trello_card_description == "Card description"
        assert job.trello_card_date == date(2023, 2, 1)
        assert job.last_updated_at == datetime(2023, 1, 20, 10, 0, 0)
        assert job.source_of_update == "Trello"
    
    @pytest.mark.unit
    def test_job_repr(self):
        """Test Job string representation."""
        job = Job(
            job=123,
            release="V456",
            job_name="Test Job Name"
        )
        
        result = repr(job)
        assert "123" in result
        assert "V456" in result
        assert "Test Job Name" in result


class TestSyncStatus:
    """Test SyncStatus enum."""
    
    @pytest.mark.unit
    def test_sync_status_values(self):
        """Test SyncStatus enum values."""
        assert SyncStatus.PENDING.value == "pending"
        assert SyncStatus.IN_PROGRESS.value == "in_progress"
        assert SyncStatus.COMPLETED.value == "completed"
        assert SyncStatus.FAILED.value == "failed"
        assert SyncStatus.SKIPPED.value == "skipped"
    
    @pytest.mark.unit
    def test_sync_status_enum_members(self):
        """Test SyncStatus enum members."""
        all_statuses = list(SyncStatus)
        assert len(all_statuses) == 5
        assert SyncStatus.PENDING in all_statuses
        assert SyncStatus.IN_PROGRESS in all_statuses
        assert SyncStatus.COMPLETED in all_statuses
        assert SyncStatus.FAILED in all_statuses
        assert SyncStatus.SKIPPED in all_statuses
