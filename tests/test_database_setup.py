"""
Test database setup and verify it's working correctly.
"""
import pytest
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus


@pytest.mark.unit
@pytest.mark.database
def test_database_connection(app_context):
    """Test that database connection is working."""
    # This should not raise an exception
    result = db.session.execute("SELECT 1").scalar()
    assert result == 1


@pytest.mark.unit
@pytest.mark.database 
def test_database_tables_exist(app_context):
    """Test that all required tables exist."""
    # Check that we can query each table without error
    Job.query.count()  # Should not raise
    SyncOperation.query.count()  # Should not raise
    SyncLog.query.count()  # Should not raise


@pytest.mark.unit
@pytest.mark.database
def test_database_constraints(app_context):
    """Test database constraints are working."""
    # Test unique constraint on Job
    job1 = Job(job=123, release="456", job_name="Test Job 1")
    job2 = Job(job=123, release="456", job_name="Test Job 2")  # Same job/release
    
    db.session.add(job1)
    db.session.commit()
    
    db.session.add(job2)
    
    # This should raise an integrity error
    with pytest.raises(Exception):  # SQLAlchemy will wrap the integrity error
        db.session.commit()
    
    # Rollback the failed transaction
    db.session.rollback()


@pytest.mark.unit
@pytest.mark.database
def test_database_cleanup_between_tests():
    """Test that database is properly cleaned between tests."""
    # Check that tables are empty
    assert Job.query.count() == 0
    assert SyncOperation.query.count() == 0
    assert SyncLog.query.count() == 0
