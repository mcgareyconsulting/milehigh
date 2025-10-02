#!/usr/bin/env python3
"""
Simple test setup checker that doesn't require all dependencies.
"""
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def mock_missing_modules():
    """Mock modules that might not be installed."""
    # Mock structlog
    sys.modules['structlog'] = MagicMock()
    
    # Mock apscheduler
    sys.modules['apscheduler'] = MagicMock()
    sys.modules['apscheduler.schedulers'] = MagicMock()
    sys.modules['apscheduler.schedulers.background'] = MagicMock()

def test_basic_imports():
    """Test that basic imports work."""
    print("Testing basic imports...")
    
    try:
        from app.models import db, Job, SyncOperation, SyncLog, SyncStatus
        print("✅ Models imported successfully")
        
        # Test that we can create instances
        job = Job(job=123, release="456", job_name="Test")
        print("✅ Job model instance created")
        
        op = SyncOperation(operation_id="test", operation_type="test", status=SyncStatus.PENDING)
        print("✅ SyncOperation model instance created")
        
        log = SyncLog(operation_id="test", level="INFO", message="Test")
        print("✅ SyncLog model instance created")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_database_setup():
    """Test database setup without full Flask app."""
    print("\nTesting database setup...")
    
    try:
        from flask import Flask
        from app.models import db, Job, SyncOperation, SyncLog
        
        # Create minimal Flask app
        app = Flask(__name__)
        
        # Create temporary database
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        
        app.config.update({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        })
        
        # Initialize database
        db.init_app(app)
        
        with app.app_context():
            # Create tables
            db.create_all()
            print("✅ Database tables created")
            
            # Test creating a record
            job = Job(job=999, release="999", job_name="Test Job")
            db.session.add(job)
            db.session.commit()
            print("✅ Test record created")
            
            # Test querying
            found_job = Job.query.filter_by(job=999).first()
            assert found_job is not None
            assert found_job.job_name == "Test Job"
            print("✅ Test record queried successfully")
            
            # Test deleting
            db.session.delete(found_job)
            db.session.commit()
            print("✅ Test record deleted")
            
            # Verify deletion
            found_job = Job.query.filter_by(job=999).first()
            assert found_job is None
            print("✅ Deletion verified")
        
        # Clean up
        os.close(db_fd)
        os.unlink(db_path)
        print("✅ Database cleanup completed")
        
        return True
        
    except Exception as e:
        print(f"❌ Database setup error: {e}")
        return False

def test_unique_constraints():
    """Test database unique constraints."""
    print("\nTesting unique constraints...")
    
    try:
        from flask import Flask
        from app.models import db, Job
        from sqlalchemy.exc import IntegrityError
        
        # Create minimal Flask app
        app = Flask(__name__)
        
        # Create temporary database
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        
        app.config.update({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        })
        
        # Initialize database
        db.init_app(app)
        
        with app.app_context():
            db.create_all()
            
            # Create first job
            job1 = Job(job=123, release="456", job_name="First Job")
            db.session.add(job1)
            db.session.commit()
            print("✅ First job created")
            
            # Try to create duplicate
            job2 = Job(job=123, release="456", job_name="Second Job")
            db.session.add(job2)
            
            try:
                db.session.commit()
                print("❌ Duplicate job was allowed (constraint not working)")
                return False
            except IntegrityError:
                print("✅ Unique constraint working (duplicate rejected)")
                db.session.rollback()
            
            # Verify first job still exists
            found_job = Job.query.filter_by(job=123, release="456").first()
            assert found_job is not None
            assert found_job.job_name == "First Job"
            print("✅ Original job still exists after rollback")
        
        # Clean up
        os.close(db_fd)
        os.unlink(db_path)
        
        return True
        
    except Exception as e:
        print(f"❌ Constraint test error: {e}")
        return False

def main():
    """Main test function."""
    print("🧪 Testing database setup...")
    
    # Mock missing modules
    mock_missing_modules()
    
    # Run tests
    tests = [
        test_basic_imports,
        test_database_setup,
        test_unique_constraints
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All database setup tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
