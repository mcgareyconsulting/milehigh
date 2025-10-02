"""
Pytest configuration and fixtures for the Trello-OneDrive sync application.
"""
import pytest
import os
import tempfile
from datetime import datetime, date
from unittest.mock import Mock, patch
import pandas as pd
from flask import Flask

# Import app modules
from app import create_app
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus
from app.config import Config


@pytest.fixture(scope="session")
def app():
    """Create and configure a test Flask application."""
    # Create a temporary database for testing
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    
    # Use the actual create_app function but with test config
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    
    # Import here to avoid circular imports
    from app import create_app
    
    # Create the app with test configuration
    test_app = create_app()
    test_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {
            'pool_pre_ping': True,
            'pool_recycle': 300,
        }
    })
    
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
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Create an application context for testing."""
    with app.app_context():
        # Ensure tables exist
        db.create_all()
        yield app


@pytest.fixture
def db_session(app_context):
    """Create a database session for testing."""
    # Clear all tables before each test
    db.session.query(SyncLog).delete()
    db.session.query(SyncOperation).delete() 
    db.session.query(Job).delete()
    db.session.commit()
    
    # Start a transaction
    db.session.begin()
    yield db.session
    
    # Rollback any changes
    db.session.rollback()
    
    # Clean up after the test
    db.session.query(SyncLog).delete()
    db.session.query(SyncOperation).delete()
    db.session.query(Job).delete()
    db.session.commit()


@pytest.fixture
def sample_job():
    """Create a sample Job record for testing."""
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


@pytest.fixture
def sample_sync_operation():
    """Create a sample SyncOperation record for testing."""
    return SyncOperation(
        operation_id="test_op_123",
        operation_type="trello_webhook",
        status=SyncStatus.PENDING,
        source_system="trello",
        source_id="test_card_123",
        records_processed=0,
        records_updated=0,
        records_created=0,
        records_failed=0
    )


@pytest.fixture
def sample_sync_log():
    """Create a sample SyncLog record for testing."""
    return SyncLog(
        operation_id="test_op_123",
        level="INFO",
        message="Test log message",
        job_id=1,
        trello_card_id="test_card_123",
        excel_identifier="123-456",
        data={"test": "data"}
    )


@pytest.fixture
def mock_trello_webhook_data():
    """Sample Trello webhook data for testing."""
    return {
        "action": {
            "type": "updateCard",
            "date": "2024-01-15T12:30:00.000Z",
            "data": {
                "card": {
                    "id": "test_card_123",
                    "name": "123-456 Updated Job Name"
                },
                "listBefore": {
                    "id": "list_before_123",
                    "name": "In Progress"
                },
                "listAfter": {
                    "id": "list_after_123", 
                    "name": "Paint complete"
                }
            }
        }
    }


@pytest.fixture
def mock_trello_card_data():
    """Sample Trello card data from API."""
    return {
        "id": "test_card_123",
        "name": "123-456 Test Job",
        "desc": "Test card description",
        "idList": "test_list_123",
        "due": "2024-02-01T18:00:00.000Z",
        "labels": []
    }


@pytest.fixture
def mock_excel_dataframe():
    """Sample Excel DataFrame for testing."""
    return pd.DataFrame({
        "Job #": [123, 124, 125],
        "Release #": [456, 457, 458],
        "Job": ["Test Job 1", "Test Job 2", "Test Job 3"],
        "Description": ["Desc 1", "Desc 2", "Desc 3"],
        "Fab Hrs": [10.5, 12.0, 8.5],
        "Install HRS": [8.0, 10.0, 6.0],
        "Paint color": ["Blue", "Red", "Green"],
        "PM": ["John", "Jane", "Bob"],
        "BY": ["Alice", "Charlie", "Dave"],
        "Released": [date(2024, 1, 15), date(2024, 1, 16), date(2024, 1, 17)],
        "Fab Order": [1.0, 2.0, 3.0],
        "Cut start": ["X", "O", ""],
        "Fitup comp": ["X", "X", "O"],
        "Welded": ["O", "X", ""],
        "Paint Comp": ["", "X", ""],
        "Ship": ["", "O", ""],
        "Start install": [date(2024, 2, 1), date(2024, 2, 2), date(2024, 2, 3)],
        "Comp. ETA": [date(2024, 2, 15), date(2024, 2, 16), date(2024, 2, 17)],
        "Job Comp": ["", "", ""],
        "Invoiced": ["", "", ""],
        "Notes": ["Note 1", "Note 2", "Note 3"],
        "start_install_formula": ["", "=TODAY()+7", ""],
        "start_install_formulaTF": [False, True, False]
    })


@pytest.fixture
def mock_onedrive_data():
    """Sample OneDrive polling data."""
    def _create_data(last_modified_time="2024-01-15T12:30:00.000Z", dataframe=None):
        if dataframe is None:
            dataframe = pd.DataFrame({
                "Job #": [123],
                "Release #": [456],
                "Job": ["Test Job"],
                "Description": ["Test description"],
                "Fab Hrs": [10.5],
                "Install HRS": [8.0],
                "Paint color": ["Blue"],
                "PM": ["John"],
                "BY": ["Jane"],
                "Released": [date(2024, 1, 15)],
                "Fab Order": [1.0],
                "Cut start": ["X"],
                "Fitup comp": ["X"],
                "Welded": ["X"],
                "Paint Comp": ["X"],
                "Ship": ["O"],
                "Start install": [date(2024, 2, 1)],
                "Comp. ETA": [date(2024, 2, 15)],
                "Job Comp": [""],
                "Invoiced": [""],
                "Notes": ["Test notes"],
                "start_install_formula": [""],
                "start_install_formulaTF": [False]
            })
        
        return {
            "last_modified_time": last_modified_time,
            "data": dataframe
        }
    
    return _create_data


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    with patch.object(Config, 'TRELLO_API_KEY', 'test_api_key'), \
         patch.object(Config, 'TRELLO_TOKEN', 'test_token'), \
         patch.object(Config, 'TRELLO_BOARD_ID', 'test_board_id'), \
         patch.object(Config, 'AZURE_CLIENT_ID', 'test_client_id'), \
         patch.object(Config, 'AZURE_CLIENT_SECRET', 'test_client_secret'), \
         patch.object(Config, 'AZURE_TENANT_ID', 'test_tenant_id'), \
         patch.object(Config, 'ONEDRIVE_USER_EMAIL', 'test@example.com'), \
         patch.object(Config, 'ONEDRIVE_FILE_PATH', '/test/file.xlsx'):
        yield Config


@pytest.fixture
def mock_requests():
    """Mock requests for API calls."""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post, \
         patch('requests.put') as mock_put, \
         patch('requests.patch') as mock_patch:
        
        # Default successful responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.text = "Success"
        mock_response.raise_for_status.return_value = None
        
        mock_get.return_value = mock_response
        mock_post.return_value = mock_response
        mock_put.return_value = mock_response
        mock_patch.return_value = mock_response
        
        yield {
            'get': mock_get,
            'post': mock_post,
            'put': mock_put,
            'patch': mock_patch,
            'response': mock_response
        }


@pytest.fixture
def mock_sync_lock():
    """Mock sync lock manager for testing."""
    with patch('app.sync_lock.sync_lock_manager') as mock_manager:
        mock_manager.is_locked.return_value = False
        mock_manager.get_current_operation.return_value = None
        mock_manager.acquire_sync_lock.return_value.__enter__ = Mock()
        mock_manager.acquire_sync_lock.return_value.__exit__ = Mock()
        yield mock_manager
