"""
Pytest configuration and shared fixtures for the Trello-OneDrive sync application.
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from datetime import datetime, date
import pandas as pd

# Import the Flask app and database
from app import create_app
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "WTF_CSRF_ENABLED": False,
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()
    
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope="function")
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope="function")
def app_context(app):
    """Create application context for testing."""
    with app.app_context():
        yield app


@pytest.fixture(scope="function")
def db_session(app_context):
    """Create database session for testing."""
    # Clear any existing data
    db.session.rollback()
    
    # Clear all tables
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
    
    yield db.session
    
    # Cleanup
    db.session.rollback()


@pytest.fixture
def sample_job(db_session):
    """Create a sample Job record for testing."""
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
        notes="Test notes",
        trello_card_id="test_card_123",
        trello_card_name="Test Card",
        trello_list_id="test_list_123",
        trello_list_name="In Progress",
        trello_card_description="Test card description",
        trello_card_date=date(2023, 2, 1),
        last_updated_at=datetime(2023, 1, 20, 10, 0, 0),
        source_of_update="System"
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.fixture
def sample_sync_operation(db_session):
    """Create a sample SyncOperation record for testing."""
    sync_op = SyncOperation(
        operation_id="test_op_123",
        operation_type="test_operation",
        status=SyncStatus.PENDING,
        source_system="test",
        source_id="test_source_123"
    )
    db_session.add(sync_op)
    db_session.commit()
    return sync_op


@pytest.fixture
def sample_trello_webhook_data():
    """Sample Trello webhook data for testing."""
    return {
        "action": {
            "type": "updateCard",
            "date": "2023-01-20T15:30:00.000Z",
            "data": {
                "card": {
                    "id": "test_card_123",
                    "name": "123-V456 Test Job"
                },
                "listBefore": {"name": "In Progress"},
                "listAfter": {"name": "Paint complete"}
            }
        }
    }


@pytest.fixture
def sample_trello_card_update_data():
    """Sample Trello card update webhook data."""
    return {
        "action": {
            "type": "updateCard",
            "date": "2023-01-20T15:30:00.000Z",
            "data": {
                "card": {
                    "id": "test_card_123",
                    "name": "123-V456 Updated Job Name"
                },
                "old": {
                    "name": "123-V456 Old Job Name"
                }
            }
        }
    }


@pytest.fixture
def sample_excel_dataframe():
    """Sample Excel DataFrame for testing."""
    return pd.DataFrame([
        {
            "Job #": 123,
            "Release #": "V456",
            "Job": "Test Job",
            "Description": "Test Description",
            "Fab Hrs": 10.5,
            "Install HRS": 5.0,
            "Paint color": "Blue",
            "PM": "PM1",
            "BY": "BY1",
            "Released": pd.to_datetime("2023-01-15"),
            "Fab Order": 1.0,
            "Cut start": "X",
            "Fitup comp": "X",
            "Welded": "X",
            "Paint Comp": "X",
            "Ship": "O",
            "Start install": pd.to_datetime("2023-02-01"),
            "Comp. ETA": pd.to_datetime("2023-02-15"),
            "Job Comp": "",
            "Invoiced": "",
            "Notes": "Test notes",
            "start_install_formula": "",
            "start_install_formulaTF": False
        }
    ])


@pytest.fixture
def mock_trello_api():
    """Mock Trello API responses."""
    with patch('app.trello.api.get_trello_card_by_id') as mock_get_card, \
         patch('app.trello.api.get_list_name_by_id') as mock_get_list_name, \
         patch('app.trello.api.get_list_by_name') as mock_get_list, \
         patch('app.trello.api.update_trello_card') as mock_update_card:
        
        mock_get_card.return_value = {
            "id": "test_card_123",
            "name": "123-V456 Test Job",
            "desc": "Test description",
            "idList": "test_list_123",
            "due": "2023-02-01T18:00:00.000Z"
        }
        
        mock_get_list_name.return_value = "Paint complete"
        
        mock_get_list.return_value = {"id": "test_list_456"}
        
        mock_update_card.return_value = True
        
        yield {
            "get_card": mock_get_card,
            "get_list_name": mock_get_list_name,
            "get_list": mock_get_list,
            "update_card": mock_update_card
        }


@pytest.fixture
def mock_onedrive_api():
    """Mock OneDrive API responses."""
    with patch('app.onedrive.api.get_excel_dataframe') as mock_get_df, \
         patch('app.onedrive.api.get_excel_data_with_timestamp') as mock_get_data, \
         patch('app.onedrive.api.update_excel_cell') as mock_update_cell:
        
        mock_get_df.return_value = pd.DataFrame([{
            "Job #": 123,
            "Release #": "V456",
            "Job": "Test Job",
            "Fitup comp": "X",
            "Welded": "X",
            "Paint Comp": "X",
            "Ship": "O",
            "Start install": pd.to_datetime("2023-02-01"),
            "start_install_formula": "",
            "start_install_formulaTF": False
        }])
        
        mock_get_data.return_value = {
            "last_modified_time": "2023-01-20T16:00:00.000Z",
            "data": mock_get_df.return_value
        }
        
        mock_update_cell.return_value = True
        
        yield {
            "get_dataframe": mock_get_df,
            "get_data": mock_get_data,
            "update_cell": mock_update_cell
        }
