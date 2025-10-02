"""
Integration tests for complete sync flows.
"""
import pytest
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, date
import pandas as pd
from app.sync import sync_from_trello, sync_from_onedrive
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus
from app.trello.utils import parse_webhook_data
from app.onedrive.utils import run_onedrive_poll


@pytest.mark.integration
@pytest.mark.sync
@pytest.mark.slow
class TestTrelloSyncFlow:
    """Integration tests for Trello sync flow."""
    
    @patch('app.sync.get_trello_card_by_id')
    @patch('app.sync.get_list_name_by_id')
    @patch('app.sync.update_excel_cell')
    @patch('app.sync.get_excel_row_and_index_by_identifiers')
    def test_trello_card_move_sync_flow(self, mock_get_excel_row, mock_update_cell, 
                                       mock_get_list_name, mock_get_card, app_context):
        """Test complete Trello card move sync flow."""
        # Setup existing job
        existing_job = Job(
            job=123,
            release="456",
            job_name="Test Job",
            trello_card_id="test_card_123",
            trello_list_name="In Progress",
            last_updated_at=datetime(2024, 1, 10, 12, 0, 0),
            source_of_update="Excel"
        )
        db.session.add(existing_job)
        db.session.commit()
        
        # Mock Trello API responses
        mock_get_card.return_value = {
            "id": "test_card_123",
            "name": "123-456 Test Job Updated",
            "desc": "Updated description",
            "idList": "new_list_123",
            "due": "2024-02-01T18:00:00.000Z"
        }
        mock_get_list_name.return_value = "Paint complete"
        
        # Mock Excel update
        mock_get_excel_row.return_value = (15, Mock())  # Row 15
        mock_update_cell.return_value = True
        
        # Create webhook event
        event_info = {
            "event": "card_moved",
            "handled": True,
            "card_id": "test_card_123",
            "card_name": "123-456 Test Job Updated",
            "from": "In Progress",
            "to": "Paint complete",
            "time": "2024-01-15T12:30:00.000Z"
        }
        
        # Execute sync
        sync_from_trello(event_info)
        
        # Verify job was updated
        updated_job = Job.query.filter_by(trello_card_id="test_card_123").first()
        assert updated_job is not None
        assert updated_job.trello_card_name == "123-456 Test Job Updated"
        assert updated_job.trello_list_name == "Paint complete"
        assert updated_job.fitup_comp == "X"
        assert updated_job.welded == "X"
        assert updated_job.paint_comp == "X"
        assert updated_job.ship == "O"
        assert updated_job.source_of_update == "Trello"
        
        # Verify Excel cells were updated
        expected_updates = [
            ("M15", "X"),  # fitup_comp
            ("N15", "X"),  # welded
            ("O15", "X"),  # paint_comp
            ("P15", "O")   # ship
        ]
        
        assert mock_update_cell.call_count == 4
        for i, (cell, value) in enumerate(expected_updates):
            call_args = mock_update_cell.call_args_list[i]
            assert call_args[0][0] == cell
            assert call_args[0][1] == value
        
        # Verify sync operation was created and completed
        sync_ops = SyncOperation.query.filter_by(operation_type="trello_webhook").all()
        assert len(sync_ops) == 1
        assert sync_ops[0].status == SyncStatus.COMPLETED
        assert sync_ops[0].source_id == "test_card_123"
        assert sync_ops[0].records_updated == 1
    
    @patch('app.sync.get_trello_card_by_id')
    def test_trello_sync_card_not_found(self, mock_get_card, app_context):
        """Test Trello sync when card is not found."""
        mock_get_card.return_value = None
        
        event_info = {
            "event": "card_updated",
            "handled": True,
            "card_id": "nonexistent_card",
            "time": "2024-01-15T12:30:00.000Z"
        }
        
        sync_from_trello(event_info)
        
        # Verify sync operation failed
        sync_ops = SyncOperation.query.filter_by(operation_type="trello_webhook").all()
        assert len(sync_ops) == 1
        assert sync_ops[0].status == SyncStatus.FAILED
        assert sync_ops[0].error_type == "CardNotFound"
    
    def test_trello_sync_duplicate_event(self, app_context):
        """Test Trello sync with duplicate event (older timestamp)."""
        # Setup existing job with recent update
        existing_job = Job(
            job=123,
            release="456",
            job_name="Test Job",
            trello_card_id="test_card_123",
            last_updated_at=datetime(2024, 1, 15, 14, 0, 0),  # Newer than event
            source_of_update="Trello"
        )
        db.session.add(existing_job)
        db.session.commit()
        
        # Create older event
        event_info = {
            "event": "card_updated",
            "handled": True,
            "card_id": "test_card_123",
            "time": "2024-01-15T12:30:00.000Z"  # Older than job's last update
        }
        
        sync_from_trello(event_info)
        
        # Verify sync operation was skipped
        sync_ops = SyncOperation.query.filter_by(operation_type="trello_webhook").all()
        assert len(sync_ops) == 1
        assert sync_ops[0].status == SyncStatus.SKIPPED


@pytest.mark.integration
@pytest.mark.sync
@pytest.mark.slow
class TestOneDriveSyncFlow:
    """Integration tests for OneDrive sync flow."""
    
    @patch('app.sync.get_list_by_name')
    @patch('app.sync.update_trello_card')
    def test_onedrive_sync_flow_with_trello_update(self, mock_update_trello, mock_get_list, 
                                                  app_context, mock_onedrive_data):
        """Test complete OneDrive sync flow with Trello updates."""
        # Setup existing job
        existing_job = Job(
            job=123,
            release="456",
            job_name="Test Job",
            trello_card_id="test_card_123",
            trello_list_name="In Progress",
            fitup_comp="O",
            welded="",
            paint_comp="",
            ship="",
            start_install=date(2024, 1, 15),
            last_updated_at=datetime(2024, 1, 10, 12, 0, 0),
            source_of_update="Trello"
        )
        db.session.add(existing_job)
        db.session.commit()
        
        # Mock Trello API responses
        mock_get_list.return_value = {"id": "paint_list_123", "name": "Paint complete"}
        mock_update_trello.return_value = {"success": True}
        
        # Create OneDrive data with updates
        excel_data = mock_onedrive_data(
            last_modified_time="2024-01-15T14:30:00.000Z",  # Newer than job
            dataframe=pd.DataFrame({
                "Job #": [123],
                "Release #": [456],
                "Job": ["Test Job Updated"],
                "Description": ["Updated description"],
                "Fab Hrs": [12.0],
                "Install HRS": [9.0],
                "Paint color": ["Red"],
                "PM": ["Jane"],
                "BY": ["Bob"],
                "Released": [date(2024, 1, 16)],
                "Fab Order": [2.0],
                "Cut start": ["X"],
                "Fitup comp": ["X"],
                "Welded": ["X"],
                "Paint Comp": ["X"],
                "Ship": ["O"],
                "Start install": [date(2024, 2, 5)],
                "Comp. ETA": [date(2024, 2, 20)],
                "Job Comp": [""],
                "Invoiced": [""],
                "Notes": ["Updated notes"],
                "start_install_formula": [""],
                "start_install_formulaTF": [False]
            })
        )
        
        # Execute sync
        sync_from_onedrive(excel_data)
        
        # Verify job was updated
        updated_job = Job.query.filter_by(job=123, release="456").first()
        assert updated_job is not None
        assert updated_job.fitup_comp == "X"
        assert updated_job.welded == "X"
        assert updated_job.paint_comp == "X"
        assert updated_job.ship == "O"
        assert updated_job.start_install == date(2024, 2, 5)
        assert updated_job.source_of_update == "Excel"
        
        # Verify Trello card was updated
        mock_update_trello.assert_called_once()
        call_args = mock_update_trello.call_args
        assert call_args[0][0] == "test_card_123"  # card_id
        assert call_args[0][1] == "paint_list_123"  # new_list_id
        assert call_args[0][2] == date(2024, 2, 5)  # new_due_date
        
        # Verify sync operation completed
        sync_ops = SyncOperation.query.filter_by(operation_type="onedrive_poll").all()
        assert len(sync_ops) == 1
        assert sync_ops[0].status == SyncStatus.COMPLETED
    
    def test_onedrive_sync_with_formula_field(self, app_context, mock_onedrive_data):
        """Test OneDrive sync with formula-driven date field."""
        # Setup existing job
        existing_job = Job(
            job=124,
            release="457",
            job_name="Formula Job",
            trello_card_id="formula_card_123",
            start_install=date(2024, 1, 20),
            start_install_formula="",
            start_install_formulaTF=False,
            last_updated_at=datetime(2024, 1, 10, 12, 0, 0),
            source_of_update="Excel"
        )
        db.session.add(existing_job)
        db.session.commit()
        
        # Create OneDrive data with formula field
        excel_data = mock_onedrive_data(
            last_modified_time="2024-01-15T14:30:00.000Z",
            dataframe=pd.DataFrame({
                "Job #": [124],
                "Release #": [457],
                "Job": ["Formula Job"],
                "Description": ["Formula job description"],
                "Fab Hrs": [10.0],
                "Install HRS": [8.0],
                "Paint color": ["Blue"],
                "PM": ["John"],
                "BY": ["Jane"],
                "Released": [date(2024, 1, 15)],
                "Fab Order": [1.0],
                "Cut start": ["X"],
                "Fitup comp": ["O"],
                "Welded": [""],
                "Paint Comp": [""],
                "Ship": [""],
                "Start install": [date(2024, 2, 10)],  # Calculated by formula
                "Comp. ETA": [date(2024, 2, 25)],
                "Job Comp": [""],
                "Invoiced": [""],
                "Notes": ["Notes"],
                "start_install_formula": ["=TODAY()+15"],
                "start_install_formulaTF": [True]
            })
        )
        
        # Execute sync (should not update Trello due date for formula fields)
        with patch('app.sync.update_trello_card') as mock_update_trello:
            sync_from_onedrive(excel_data)
            
            # Trello should not be updated for formula-driven fields
            mock_update_trello.assert_not_called()
        
        # Verify job was updated in database
        updated_job = Job.query.filter_by(job=124, release="457").first()
        assert updated_job is not None
        assert updated_job.start_install == date(2024, 2, 10)
        assert updated_job.start_install_formula == "=TODAY()+15"
        assert updated_job.start_install_formulaTF is True
    
    def test_onedrive_sync_no_data(self, app_context):
        """Test OneDrive sync with no data."""
        sync_from_onedrive(None)
        
        # Verify sync operation was skipped
        sync_ops = SyncOperation.query.filter_by(operation_type="onedrive_poll").all()
        assert len(sync_ops) == 1
        assert sync_ops[0].status == SyncStatus.SKIPPED
    
    def test_onedrive_sync_invalid_data_format(self, app_context):
        """Test OneDrive sync with invalid data format."""
        invalid_data = {"invalid": "format"}
        
        sync_from_onedrive(invalid_data)
        
        # Verify sync operation failed
        sync_ops = SyncOperation.query.filter_by(operation_type="onedrive_poll").all()
        assert len(sync_ops) == 1
        assert sync_ops[0].status == SyncStatus.FAILED
        assert sync_ops[0].error_type == "InvalidPayload"


@pytest.mark.integration
@pytest.mark.sync
class TestWebhookParsing:
    """Integration tests for webhook parsing and handling."""
    
    def test_webhook_parsing_card_moved(self, mock_trello_webhook_data):
        """Test parsing card moved webhook data."""
        result = parse_webhook_data(mock_trello_webhook_data)
        
        assert result["event"] == "card_moved"
        assert result["handled"] is True
        assert result["card_id"] == "test_card_123"
        assert result["from"] == "In Progress"
        assert result["to"] == "Paint complete"
        assert result["time"] == "2024-01-15T12:30:00.000Z"
    
    def test_webhook_parsing_card_field_update(self):
        """Test parsing card field update webhook data."""
        webhook_data = {
            "action": {
                "type": "updateCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "test_card_456",
                        "name": "Updated Card Name"
                    },
                    "old": {
                        "name": "Old Card Name",
                        "desc": "Old description",
                        "due": "2024-01-01T18:00:00.000Z"
                    }
                }
            }
        }
        
        result = parse_webhook_data(webhook_data)
        
        assert result["event"] == "card_updated"
        assert result["handled"] is True
        assert result["card_id"] == "test_card_456"
        assert "name" in result["changed_fields"]
        assert "desc" in result["changed_fields"]
        assert "due" in result["changed_fields"]


@pytest.mark.integration
@pytest.mark.sync
class TestOneDrivePolling:
    """Integration tests for OneDrive polling."""
    
    @patch('app.onedrive.utils.get_excel_data_with_timestamp')
    @patch('app.sync.sync_from_onedrive')
    def test_run_onedrive_poll_success(self, mock_sync, mock_get_data, mock_sync_lock):
        """Test successful OneDrive polling."""
        # Mock data
        test_data = {
            "last_modified_time": "2024-01-15T12:30:00.000Z",
            "data": pd.DataFrame({"Job #": [123], "Release #": [456]})
        }
        mock_get_data.return_value = test_data
        
        result = run_onedrive_poll()
        
        # Verify functions were called
        mock_get_data.assert_called_once()
        mock_sync.assert_called_once_with(test_data)
        
        assert result == test_data
    
    @patch('app.onedrive.utils.get_excel_data_with_timestamp')
    def test_run_onedrive_poll_no_data(self, mock_get_data, mock_sync_lock):
        """Test OneDrive polling with no data."""
        mock_get_data.return_value = None
        
        with patch('app.sync.sync_from_onedrive') as mock_sync:
            result = run_onedrive_poll()
            
            mock_sync.assert_called_once_with(None)
            assert result is None
