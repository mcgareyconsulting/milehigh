"""
Simplified test configuration that avoids importing the full app.
Use this for unit tests that don't need the full Flask application.
"""
import pytest
import os
import tempfile
from datetime import datetime, date
from unittest.mock import Mock, patch
import pandas as pd
from flask import Flask

# Import only the models we need
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus


@pytest.fixture(scope="session")
def simple_app():
    """Create a minimal Flask application for unit tests."""
    # Create a temporary database for testing
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    
    # Create minimal test app
    test_app = Flask(__name__)
    test_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'WTF_CSRF_ENABLED': False,
    })
    
    # Initialize database
    db.init_app(test_app)
    
    with test_app.app_context():
        db.create_all()
        yield test_app
        
        # Clean up database
        try:
            db.drop_all()
        except Exception:
            pass
    
    # Clean up temporary file
    try:
        os.close(db_fd)
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def simple_app_context(simple_app):
    """Create an application context for unit testing."""
    with simple_app.app_context():
        # Ensure tables exist
        db.create_all()
        yield simple_app


@pytest.fixture
def clean_db(simple_app_context):
    """Provide a clean database for each test."""
    # Clear all tables before test
    db.session.query(SyncLog).delete()
    db.session.query(SyncOperation).delete()
    db.session.query(Job).delete()
    db.session.commit()
    
    yield db.session
    
    # Clean up after test
    try:
        db.session.query(SyncLog).delete()
        db.session.query(SyncOperation).delete()
        db.session.query(Job).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()


@pytest.fixture
def sample_job_simple():
    """Create a sample Job record for unit testing."""
    return Job(
        job=123,
        release="456",
        job_name="Test Job",
        description="Test job description",
        fab_hrs=10.5,
        install_hrs=8.0,
        paint_color="Blue",
        pm="John",
        by="Jane",
        released=date(2024, 1, 15),
        fab_order=1.0,
        cut_start="X",
        fitup_comp="O",
        welded="",
        paint_comp="",
        ship="",
        start_install=date(2024, 2, 1),
        comp_eta=date(2024, 2, 15),
        job_comp="",
        invoiced="",
        notes="Test notes",
        trello_card_id="test_card_123",
        trello_card_name="123-456 Test Job",
        trello_list_id="test_list_123",
        trello_list_name="In Progress",
        trello_card_description="Test card description",
        trello_card_date=date(2024, 2, 1),
        last_updated_at=datetime(2024, 1, 10, 12, 0, 0),
        source_of_update="Excel"
    )
