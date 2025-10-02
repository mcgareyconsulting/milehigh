"""
Unit tests for database models.
"""
import pytest
from datetime import datetime, date
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus, query_job_releases


@pytest.mark.unit
@pytest.mark.database
class TestJobModel:
    """Test the Job model."""
    
    def test_job_creation(self, app_context, sample_job):
        """Test creating a Job record."""
        # Clear any existing data first
        Job.query.delete()
        db.session.commit()
        
        db.session.add(sample_job)
        db.session.commit()
        
        # Verify the job was created
        job = Job.query.filter_by(job=123, release="456").first()
        assert job is not None
        assert job.job_name == "Test Job"
        assert job.trello_card_id == "test_card_123"
    
    def test_job_unique_constraint(self, app_context, sample_job):
        """Test that job/release combination is unique."""
        # Clear any existing data first
        Job.query.delete()
        db.session.commit()
        
        db.session.add(sample_job)
        db.session.commit()
        
        # Try to create another job with same job/release
        duplicate_job = Job(
            job=123,
            release="456",
            job_name="Duplicate Job"
        )
        db.session.add(duplicate_job)
        
        with pytest.raises(Exception):  # Should raise integrity error
            db.session.commit()
        
        # Clean up the failed transaction
        db.session.rollback()
    
    def test_job_repr(self, sample_job):
        """Test Job string representation."""
        expected = "<Job 123 - 456 - Test Job>"
        assert repr(sample_job) == expected
    
    def test_job_fields(self, sample_job):
        """Test all Job model fields are accessible."""
        # Test required fields
        assert sample_job.job == 123
        assert sample_job.release == "456"
        assert sample_job.job_name == "Test Job"
        
        # Test Excel fields
        assert sample_job.description == "Test job description"
        assert sample_job.fab_hrs == 10.5
        assert sample_job.install_hrs == 8.0
        assert sample_job.paint_color == "Blue"
        assert sample_job.pm == "John"
        assert sample_job.by == "Jane"
        assert sample_job.released == date(2024, 1, 15)
        assert sample_job.fab_order == 1.0
        assert sample_job.cut_start == "X"
        assert sample_job.fitup_comp == "O"
        assert sample_job.welded == ""
        assert sample_job.paint_comp == ""
        assert sample_job.ship == ""
        assert sample_job.start_install == date(2024, 2, 1)
        assert sample_job.comp_eta == date(2024, 2, 15)
        assert sample_job.job_comp == ""
        assert sample_job.invoiced == ""
        assert sample_job.notes == "Test notes"
        
        # Test Trello fields
        assert sample_job.trello_card_id == "test_card_123"
        assert sample_job.trello_card_name == "123-456 Test Job"
        assert sample_job.trello_list_id == "test_list_123"
        assert sample_job.trello_list_name == "In Progress"
        assert sample_job.trello_card_description == "Test card description"
        assert sample_job.trello_card_date == date(2024, 2, 1)
        
        # Test tracking fields
        assert sample_job.last_updated_at == datetime(2024, 1, 10, 12, 0, 0)
        assert sample_job.source_of_update == "Excel"


@pytest.mark.unit
@pytest.mark.database
class TestSyncOperationModel:
    """Test the SyncOperation model."""
    
    def test_sync_operation_creation(self, app_context, sample_sync_operation):
        """Test creating a SyncOperation record."""
        # Clear any existing data first
        SyncOperation.query.delete()
        db.session.commit()
        
        db.session.add(sample_sync_operation)
        db.session.commit()
        
        # Verify the operation was created
        op = SyncOperation.query.filter_by(operation_id="test_op_123").first()
        assert op is not None
        assert op.operation_type == "trello_webhook"
        assert op.status == SyncStatus.PENDING
        assert op.source_system == "trello"
        assert op.source_id == "test_card_123"
    
    def test_sync_operation_status_enum(self, sample_sync_operation):
        """Test SyncStatus enum values."""
        # Test all enum values
        sample_sync_operation.status = SyncStatus.PENDING
        assert sample_sync_operation.status == SyncStatus.PENDING
        
        sample_sync_operation.status = SyncStatus.IN_PROGRESS
        assert sample_sync_operation.status == SyncStatus.IN_PROGRESS
        
        sample_sync_operation.status = SyncStatus.COMPLETED
        assert sample_sync_operation.status == SyncStatus.COMPLETED
        
        sample_sync_operation.status = SyncStatus.FAILED
        assert sample_sync_operation.status == SyncStatus.FAILED
        
        sample_sync_operation.status = SyncStatus.SKIPPED
        assert sample_sync_operation.status == SyncStatus.SKIPPED
    
    def test_sync_operation_to_dict(self, sample_sync_operation):
        """Test SyncOperation to_dict method."""
        result = sample_sync_operation.to_dict()
        
        assert isinstance(result, dict)
        assert result['operation_id'] == "test_op_123"
        assert result['operation_type'] == "trello_webhook"
        assert result['status'] == "pending"
        assert result['source_system'] == "trello"
        assert result['source_id'] == "test_card_123"
        assert result['records_processed'] == 0
        assert result['records_updated'] == 0
        assert result['records_created'] == 0
        assert result['records_failed'] == 0
    
    def test_sync_operation_repr(self, sample_sync_operation):
        """Test SyncOperation string representation."""
        expected = "<SyncOperation test_op_123 - trello_webhook - SyncStatus.PENDING>"
        assert repr(sample_sync_operation) == expected
    
    def test_sync_operation_timing(self, app_context, sample_sync_operation):
        """Test SyncOperation timing fields."""
        # Set timing fields
        start_time = datetime.utcnow()
        sample_sync_operation.started_at = start_time
        sample_sync_operation.completed_at = start_time
        sample_sync_operation.duration_seconds = 1.5
        
        db.session.add(sample_sync_operation)
        db.session.commit()
        
        op = SyncOperation.query.filter_by(operation_id="test_op_123").first()
        assert op.started_at == start_time
        assert op.completed_at == start_time
        assert op.duration_seconds == 1.5


@pytest.mark.unit
@pytest.mark.database
class TestSyncLogModel:
    """Test the SyncLog model."""
    
    def test_sync_log_creation(self, app_context, sample_sync_log):
        """Test creating a SyncLog record."""
        db.session.add(sample_sync_log)
        db.session.commit()
        
        # Verify the log was created
        log = SyncLog.query.filter_by(operation_id="test_op_123").first()
        assert log is not None
        assert log.level == "INFO"
        assert log.message == "Test log message"
        assert log.job_id == 1
        assert log.trello_card_id == "test_card_123"
        assert log.excel_identifier == "123-456"
        assert log.data == {"test": "data"}
    
    def test_sync_log_repr(self, sample_sync_log):
        """Test SyncLog string representation."""
        expected = "<SyncLog test_op_123 - INFO - Test log message...>"
        assert repr(sample_sync_log) == expected
    
    def test_sync_log_timestamp_default(self, app_context):
        """Test SyncLog timestamp defaults to current time."""
        before = datetime.utcnow()
        log = SyncLog(
            operation_id="test_op",
            level="INFO",
            message="Test message"
        )
        db.session.add(log)
        db.session.commit()
        after = datetime.utcnow()
        
        assert before <= log.timestamp <= after


@pytest.mark.unit
@pytest.mark.database
class TestQueryJobReleases:
    """Test the query_job_releases function."""
    
    def test_query_job_releases_empty(self, app_context):
        """Test query_job_releases with no data."""
        df = query_job_releases()
        assert df.empty
        assert len(df.columns) > 0  # Should have column structure
    
    def test_query_job_releases_with_data(self, app_context, sample_job):
        """Test query_job_releases with sample data."""
        db.session.add(sample_job)
        db.session.commit()
        
        df = query_job_releases()
        assert len(df) == 1
        
        # Check column mapping
        row = df.iloc[0]
        assert row["Job #"] == 123
        assert row["Release #"] == "456"
        assert row["Job"] == "Test Job"
        assert row["Description"] == "Test job description"
        assert row["Fab Hrs"] == 10.5
        assert row["Install HRS"] == 8.0
        assert row["Paint color"] == "Blue"
        assert row["PM"] == "John"
        assert row["BY"] == "Jane"
        assert row["Released"] == date(2024, 1, 15)
        assert row["Fab Order"] == 1.0
        assert row["Cut start"] == "X"
        assert row["Fitup comp"] == "O"
        assert row["Welded"] == ""
        assert row["Paint Comp"] == ""
        assert row["Ship"] == ""
        assert row["Start install"] == date(2024, 2, 1)
        assert row["Comp. ETA"] == date(2024, 2, 15)
        assert row["Job Comp"] == ""
        assert row["Invoiced"] == ""
        assert row["Notes"] == "Test notes"
    
    def test_query_job_releases_multiple_jobs(self, app_context):
        """Test query_job_releases with multiple jobs."""
        # Create multiple jobs
        jobs = [
            Job(job=123, release="456", job_name="Job 1"),
            Job(job=124, release="457", job_name="Job 2"),
            Job(job=125, release="458", job_name="Job 3")
        ]
        
        for job in jobs:
            db.session.add(job)
        db.session.commit()
        
        df = query_job_releases()
        assert len(df) == 3
        
        # Check all jobs are present
        job_numbers = df["Job #"].tolist()
        assert 123 in job_numbers
        assert 124 in job_numbers
        assert 125 in job_numbers
