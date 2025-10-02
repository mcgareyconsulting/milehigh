"""
Tests to verify database isolation between tests.
"""
import pytest
from app.models import db, Job


@pytest.mark.unit
@pytest.mark.database
class TestDatabaseIsolation:
    """Test that database state is properly isolated between tests."""
    
    def test_database_starts_clean(self, app_context):
        """Test that database starts with no records."""
        job_count = Job.query.count()
        assert job_count == 0
    
    def test_create_job_first(self, app_context):
        """Create a job in the first test."""
        job = Job(job=100, release="200", job_name="First Test Job")
        db.session.add(job)
        db.session.commit()
        
        # Verify job was created
        assert Job.query.count() == 1
        assert Job.query.first().job_name == "First Test Job"
    
    def test_database_clean_after_previous_test(self, app_context):
        """Test that database is clean after previous test."""
        # This should pass if isolation is working
        job_count = Job.query.count()
        assert job_count == 0
    
    def test_create_job_second(self, app_context):
        """Create a job in the second test with same ID."""
        # This should work if the previous job was cleaned up
        job = Job(job=100, release="200", job_name="Second Test Job")
        db.session.add(job)
        db.session.commit()
        
        # Verify job was created
        assert Job.query.count() == 1
        assert Job.query.first().job_name == "Second Test Job"
    
    def test_multiple_jobs_same_test(self, app_context):
        """Test creating multiple jobs in the same test."""
        jobs = [
            Job(job=101, release="201", job_name="Job 1"),
            Job(job=102, release="202", job_name="Job 2"),
            Job(job=103, release="203", job_name="Job 3")
        ]
        
        for job in jobs:
            db.session.add(job)
        db.session.commit()
        
        assert Job.query.count() == 3
        
        # Verify all jobs exist
        job_names = [job.job_name for job in Job.query.all()]
        assert "Job 1" in job_names
        assert "Job 2" in job_names
        assert "Job 3" in job_names
    
    def test_database_clean_after_multiple_jobs(self, app_context):
        """Test that database is clean after creating multiple jobs."""
        job_count = Job.query.count()
        assert job_count == 0
