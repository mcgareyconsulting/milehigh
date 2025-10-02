"""
Simplified unit tests for database models that don't require the full app.
"""
import pytest
from datetime import datetime, date
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus, query_job_releases


@pytest.mark.unit
@pytest.mark.database
class TestJobModelSimple:
    """Test the Job model with simplified setup."""
    
    def test_job_creation_simple(self, clean_db, sample_job_simple):
        """Test creating a Job record."""
        db.session.add(sample_job_simple)
        db.session.commit()
        
        # Verify the job was created
        job = Job.query.filter_by(job=123, release="456").first()
        assert job is not None
        assert job.job_name == "Test Job"
        assert job.trello_card_id == "test_card_123"
    
    def test_job_unique_constraint_simple(self, clean_db):
        """Test that job/release combination is unique."""
        # Create first job
        job1 = Job(job=123, release="456", job_name="First Job")
        db.session.add(job1)
        db.session.commit()
        
        # Try to create another job with same job/release
        job2 = Job(job=123, release="456", job_name="Second Job")
        db.session.add(job2)
        
        with pytest.raises(Exception):  # Should raise integrity error
            db.session.commit()
        
        # Clean up the failed transaction
        db.session.rollback()
    
    def test_job_repr_simple(self, sample_job_simple):
        """Test Job string representation."""
        expected = "<Job 123 - 456 - Test Job>"
        assert repr(sample_job_simple) == expected
    
    def test_job_fields_simple(self, sample_job_simple):
        """Test all Job model fields are accessible."""
        # Test required fields
        assert sample_job_simple.job == 123
        assert sample_job_simple.release == "456"
        assert sample_job_simple.job_name == "Test Job"
        
        # Test Excel fields
        assert sample_job_simple.description == "Test job description"
        assert sample_job_simple.fab_hrs == 10.5
        assert sample_job_simple.install_hrs == 8.0
        assert sample_job_simple.paint_color == "Blue"
        
        # Test Trello fields
        assert sample_job_simple.trello_card_id == "test_card_123"
        assert sample_job_simple.trello_card_name == "123-456 Test Job"
        assert sample_job_simple.trello_list_name == "In Progress"
        
        # Test tracking fields
        assert sample_job_simple.last_updated_at == datetime(2024, 1, 10, 12, 0, 0)
        assert sample_job_simple.source_of_update == "Excel"


@pytest.mark.unit
@pytest.mark.database
class TestSyncOperationModelSimple:
    """Test the SyncOperation model with simplified setup."""
    
    def test_sync_operation_creation_simple(self, clean_db):
        """Test creating a SyncOperation record."""
        operation = SyncOperation(
            operation_id="test_op_123",
            operation_type="trello_webhook",
            status=SyncStatus.PENDING,
            source_system="trello",
            source_id="test_card_123"
        )
        
        db.session.add(operation)
        db.session.commit()
        
        # Verify the operation was created
        op = SyncOperation.query.filter_by(operation_id="test_op_123").first()
        assert op is not None
        assert op.operation_type == "trello_webhook"
        assert op.status == SyncStatus.PENDING
        assert op.source_system == "trello"
        assert op.source_id == "test_card_123"
    
    def test_sync_operation_status_enum_simple(self):
        """Test SyncStatus enum values."""
        operation = SyncOperation(
            operation_id="test_op_456",
            operation_type="test",
            status=SyncStatus.PENDING
        )
        
        # Test all enum values
        operation.status = SyncStatus.PENDING
        assert operation.status == SyncStatus.PENDING
        
        operation.status = SyncStatus.IN_PROGRESS
        assert operation.status == SyncStatus.IN_PROGRESS
        
        operation.status = SyncStatus.COMPLETED
        assert operation.status == SyncStatus.COMPLETED
        
        operation.status = SyncStatus.FAILED
        assert operation.status == SyncStatus.FAILED
        
        operation.status = SyncStatus.SKIPPED
        assert operation.status == SyncStatus.SKIPPED
    
    def test_sync_operation_to_dict_simple(self):
        """Test SyncOperation to_dict method."""
        operation = SyncOperation(
            operation_id="test_op_789",
            operation_type="trello_webhook",
            status=SyncStatus.PENDING,
            source_system="trello",
            source_id="test_card_789"
        )
        
        result = operation.to_dict()
        
        assert isinstance(result, dict)
        assert result['operation_id'] == "test_op_789"
        assert result['operation_type'] == "trello_webhook"
        assert result['status'] == "pending"
        assert result['source_system'] == "trello"
        assert result['source_id'] == "test_card_789"


@pytest.mark.unit
@pytest.mark.database
class TestSyncLogModelSimple:
    """Test the SyncLog model with simplified setup."""
    
    def test_sync_log_creation_simple(self, clean_db):
        """Test creating a SyncLog record."""
        log = SyncLog(
            operation_id="test_op_123",
            level="INFO",
            message="Test log message",
            job_id=1,
            trello_card_id="test_card_123",
            excel_identifier="123-456",
            data={"test": "data"}
        )
        
        db.session.add(log)
        db.session.commit()
        
        # Verify the log was created
        saved_log = SyncLog.query.filter_by(operation_id="test_op_123").first()
        assert saved_log is not None
        assert saved_log.level == "INFO"
        assert saved_log.message == "Test log message"
        assert saved_log.job_id == 1
        assert saved_log.trello_card_id == "test_card_123"
        assert saved_log.excel_identifier == "123-456"
        assert saved_log.data == {"test": "data"}
    
    def test_sync_log_repr_simple(self):
        """Test SyncLog string representation."""
        log = SyncLog(
            operation_id="test_op_123",
            level="INFO",
            message="Test log message"
        )
        
        expected = "<SyncLog test_op_123 - INFO - Test log message...>"
        assert repr(log) == expected
    
    def test_sync_log_timestamp_default_simple(self, clean_db):
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
class TestQueryJobReleasesSimple:
    """Test the query_job_releases function with simplified setup."""
    
    def test_query_job_releases_empty_simple(self, clean_db):
        """Test query_job_releases with no data."""
        df = query_job_releases()
        assert df.empty
        assert len(df.columns) > 0  # Should have column structure
    
    def test_query_job_releases_with_data_simple(self, clean_db, sample_job_simple):
        """Test query_job_releases with sample data."""
        db.session.add(sample_job_simple)
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
    
    def test_query_job_releases_multiple_jobs_simple(self, clean_db):
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
