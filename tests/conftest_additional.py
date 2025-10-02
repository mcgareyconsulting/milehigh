"""
Additional test configuration and utilities.
"""
import pytest
from app.models import db, Job, SyncOperation, SyncLog


@pytest.fixture(autouse=True)
def clean_database(app_context):
    """Automatically clean database before and after each test."""
    # Clean before test
    _clean_all_tables()
    yield
    # Clean after test
    _clean_all_tables()


def _clean_all_tables():
    """Helper function to clean all database tables."""
    try:
        # Delete in reverse order of dependencies
        db.session.query(SyncLog).delete()
        db.session.query(SyncOperation).delete()
        db.session.query(Job).delete()
        db.session.commit()
    except Exception as e:
        # If deletion fails, rollback and try again
        db.session.rollback()
        try:
            # Force delete with raw SQL if needed
            db.session.execute("DELETE FROM sync_logs")
            db.session.execute("DELETE FROM sync_operations") 
            db.session.execute("DELETE FROM jobs")
            db.session.commit()
        except Exception:
            # Last resort: rollback and continue
            db.session.rollback()


@pytest.fixture
def isolated_db(app_context):
    """Provide an isolated database session that's automatically cleaned."""
    _clean_all_tables()
    
    # Start a new transaction
    transaction = db.session.begin()
    
    try:
        yield db.session
    finally:
        # Always rollback the transaction
        transaction.rollback()
        _clean_all_tables()


@pytest.fixture
def db_with_sample_data(isolated_db):
    """Provide a database session with sample data loaded."""
    from tests.fixtures.sample_data import SampleDatabaseData
    
    # Add sample data
    sample_jobs = SampleDatabaseData.job_records()
    sample_ops = SampleDatabaseData.sync_operations()
    sample_logs = SampleDatabaseData.sync_logs()
    
    for job in sample_jobs:
        db.session.add(job)
    
    for op in sample_ops:
        db.session.add(op)
    
    for log in sample_logs:
        db.session.add(log)
    
    db.session.commit()
    
    yield db.session
