"""
Integration tests for Flask routes and endpoints.
"""
import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime, date
from app.models import db, Job, SyncOperation, SyncLog, SyncStatus


@pytest.mark.integration
@pytest.mark.api
class TestFlaskRoutes:
    """Integration tests for Flask application routes."""
    
    def test_index_route(self, client):
        """Test the index route."""
        response = client.get('/')
        assert response.status_code == 200
        assert b"Welcome to the Trello OneDrive Sync App!" in response.data
    
    def test_sync_status_route(self, client, mock_sync_lock):
        """Test the sync status route."""
        # Mock sync lock status
        mock_sync_lock.get_status.return_value = {
            "is_locked": False,
            "current_operation": None,
            "timestamp": "2024-01-15T12:30:00"
        }
        
        response = client.get('/sync/status')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert "is_locked" in data
        assert "current_operation" in data
        assert "timestamp" in data
    
    def test_sync_status_route_error(self, client):
        """Test sync status route with error."""
        with patch('app.sync_lock.sync_lock_manager.get_status', side_effect=Exception("Test error")):
            response = client.get('/sync/status')
            assert response.status_code == 500
            
            data = json.loads(response.data)
            assert data["status"] == "error"
            assert "Could not get status" in data["message"]
    
    def test_sync_operations_route(self, client, app_context):
        """Test the sync operations route."""
        # Create test sync operations
        ops = [
            SyncOperation(
                operation_id="op1",
                operation_type="trello_webhook",
                status=SyncStatus.COMPLETED,
                started_at=datetime(2024, 1, 15, 12, 0, 0),
                duration_seconds=1.5
            ),
            SyncOperation(
                operation_id="op2",
                operation_type="onedrive_poll",
                status=SyncStatus.FAILED,
                started_at=datetime(2024, 1, 15, 13, 0, 0),
                error_type="APIError"
            )
        ]
        
        for op in ops:
            db.session.add(op)
        db.session.commit()
        
        response = client.get('/sync/operations')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert "operations" in data
        assert "total" in data
        assert len(data["operations"]) == 2
        
        # Check operation details
        op1_data = next(op for op in data["operations"] if op["operation_id"] == "op1")
        assert op1_data["operation_type"] == "trello_webhook"
        assert op1_data["status"] == "completed"
        assert op1_data["duration_seconds"] == 1.5
        
        op2_data = next(op for op in data["operations"] if op["operation_id"] == "op2")
        assert op2_data["operation_type"] == "onedrive_poll"
        assert op2_data["status"] == "failed"
        assert op2_data["error_type"] == "APIError"
    
    def test_sync_operations_route_with_date_filter(self, client, app_context):
        """Test sync operations route with date filtering."""
        # Create operations on different dates
        ops = [
            SyncOperation(
                operation_id="op_today",
                operation_type="trello_webhook",
                status=SyncStatus.COMPLETED,
                started_at=datetime(2024, 1, 15, 12, 0, 0)
            ),
            SyncOperation(
                operation_id="op_yesterday",
                operation_type="onedrive_poll",
                status=SyncStatus.COMPLETED,
                started_at=datetime(2024, 1, 14, 12, 0, 0)
            )
        ]
        
        for op in ops:
            db.session.add(op)
        db.session.commit()
        
        # Filter for specific date
        response = client.get('/sync/operations?start=2024-01-15&end=2024-01-15')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert len(data["operations"]) == 1
        assert data["operations"][0]["operation_id"] == "op_today"
        
        # Check filters in response
        assert data["filters"]["start"] == "2024-01-15"
        assert data["filters"]["end"] == "2024-01-15"
    
    def test_sync_operation_logs_route(self, client, app_context):
        """Test the sync operation logs route."""
        operation_id = "test_op_123"
        
        # Create test logs
        logs = [
            SyncLog(
                operation_id=operation_id,
                level="INFO",
                message="Operation started",
                timestamp=datetime(2024, 1, 15, 12, 0, 0)
            ),
            SyncLog(
                operation_id=operation_id,
                level="WARNING",
                message="Warning occurred",
                timestamp=datetime(2024, 1, 15, 12, 1, 0),
                data={"warning_type": "minor"}
            ),
            SyncLog(
                operation_id=operation_id,
                level="INFO",
                message="Operation completed",
                timestamp=datetime(2024, 1, 15, 12, 2, 0)
            )
        ]
        
        for log in logs:
            db.session.add(log)
        db.session.commit()
        
        response = client.get(f'/sync/operations/{operation_id}/logs')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data["operation_id"] == operation_id
        assert len(data["logs"]) == 3
        
        # Check logs are ordered by timestamp
        timestamps = [log["timestamp"] for log in data["logs"]]
        assert timestamps == sorted(timestamps)
        
        # Check log details
        warning_log = next(log for log in data["logs"] if log["level"] == "WARNING")
        assert warning_log["message"] == "Warning occurred"
        assert warning_log["data"]["warning_type"] == "minor"
    
    def test_sync_stats_route(self, client, app_context):
        """Test the sync stats route."""
        # Create test operations with different statuses
        recent_time = datetime.utcnow()
        ops = [
            SyncOperation(
                operation_id="op1",
                operation_type="trello_webhook",
                status=SyncStatus.COMPLETED,
                started_at=recent_time,
                duration_seconds=1.0
            ),
            SyncOperation(
                operation_id="op2",
                operation_type="onedrive_poll",
                status=SyncStatus.COMPLETED,
                started_at=recent_time,
                duration_seconds=2.0
            ),
            SyncOperation(
                operation_id="op3",
                operation_type="trello_webhook",
                status=SyncStatus.FAILED,
                started_at=recent_time,
                duration_seconds=0.5
            )
        ]
        
        for op in ops:
            db.session.add(op)
        db.session.commit()
        
        with patch('app.sync_lock.sync_lock_manager') as mock_manager:
            mock_manager.is_locked.return_value = False
            mock_manager.get_current_operation.return_value = None
            
            response = client.get('/sync/stats')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            
            # Check 24-hour stats
            stats_24h = data["last_24_hours"]
            assert stats_24h["total_operations"] == 3
            assert stats_24h["status_breakdown"]["completed"] == 2
            assert stats_24h["status_breakdown"]["failed"] == 1
            assert stats_24h["success_rate_percent"] == 66.67
            assert stats_24h["average_duration_seconds"] == 1.17  # (1.0 + 2.0 + 0.5) / 3
            
            # Check current status
            current_status = data["current_status"]
            assert current_status["sync_locked"] is False
            assert current_status["current_operation"] is None
    
    def test_sync_operations_view_route(self, client, app_context):
        """Test the sync operations HTML view route."""
        # Create test operation
        op = SyncOperation(
            operation_id="view_test_op",
            operation_type="trello_webhook",
            status=SyncStatus.COMPLETED,
            started_at=datetime(2024, 1, 15, 12, 0, 0),
            duration_seconds=1.5
        )
        db.session.add(op)
        db.session.commit()
        
        response = client.get('/sync/operations/view')
        assert response.status_code == 200
        assert b"Sync Operations" in response.data
        assert b"view_test_op" in response.data
        assert b"trello_webhook" in response.data
    
    def test_sync_operation_logs_view_route(self, client, app_context):
        """Test the sync operation logs HTML view route."""
        operation_id = "view_logs_test"
        
        # Create test log
        log = SyncLog(
            operation_id=operation_id,
            level="INFO",
            message="Test log message",
            timestamp=datetime(2024, 1, 15, 12, 0, 0)
        )
        db.session.add(log)
        db.session.commit()
        
        response = client.get(f'/sync/operations/{operation_id}/logs/view')
        assert response.status_code == 200
        assert f"Logs for operation {operation_id}".encode() in response.data
        assert b"Test log message" in response.data


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.trello
class TestTrelloWebhookRoute:
    """Integration tests for Trello webhook route."""
    
    def test_trello_webhook_head_request(self, client):
        """Test Trello webhook HEAD request (webhook verification)."""
        response = client.head('/trello/webhook')
        assert response.status_code == 200
    
    @patch('app.trello.sync_from_trello')
    @patch('app.trello.parse_webhook_data')
    def test_trello_webhook_post_handled_event(self, mock_parse, mock_sync, client, mock_sync_lock):
        """Test Trello webhook POST with handled event."""
        # Mock webhook parsing
        mock_parse.return_value = {
            "event": "card_moved",
            "handled": True,
            "card_id": "test_card_123"
        }
        
        # Mock sync lock not locked
        mock_sync_lock.is_locked.return_value = False
        
        webhook_data = {
            "action": {
                "type": "updateCard",
                "data": {
                    "card": {"id": "test_card_123"},
                    "listBefore": {"name": "To Do"},
                    "listAfter": {"name": "In Progress"}
                }
            }
        }
        
        response = client.post('/trello/webhook', 
                             data=json.dumps(webhook_data),
                             content_type='application/json')
        
        assert response.status_code == 200
        mock_parse.assert_called_once_with(webhook_data)
    
    @patch('app.trello.parse_webhook_data')
    def test_trello_webhook_post_unhandled_event(self, mock_parse, client):
        """Test Trello webhook POST with unhandled event."""
        # Mock webhook parsing for unhandled event
        mock_parse.return_value = {
            "event": "unhandled",
            "handled": False
        }
        
        webhook_data = {"action": {"type": "unknown"}}
        
        response = client.post('/trello/webhook',
                             data=json.dumps(webhook_data),
                             content_type='application/json')
        
        assert response.status_code == 200
        mock_parse.assert_called_once_with(webhook_data)
    
    @patch('app.trello.parse_webhook_data')
    def test_trello_webhook_post_when_locked(self, mock_parse, client):
        """Test Trello webhook POST when sync is locked."""
        # Mock webhook parsing
        mock_parse.return_value = {
            "event": "card_moved",
            "handled": True,
            "card_id": "test_card_123"
        }
        
        with patch('app.trello.sync_lock_manager') as mock_manager:
            mock_manager.is_locked.return_value = True
            
            with patch('app.trello.trello_event_queue') as mock_queue:
                mock_queue.put_nowait.return_value = None
                
                webhook_data = {"action": {"type": "updateCard"}}
                
                response = client.post('/trello/webhook',
                                     data=json.dumps(webhook_data),
                                     content_type='application/json')
                
                assert response.status_code == 202
                data = json.loads(response.data)
                assert data["status"] == "queued"
                
                mock_queue.put_nowait.assert_called_once()
    
    def test_trello_thread_stats_route(self, client):
        """Test Trello thread stats route."""
        response = client.get('/trello/thread-stats')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert "thread_stats" in data
        assert "sync_lock_status" in data


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.onedrive
class TestOneDriveRoute:
    """Integration tests for OneDrive route."""
    
    @patch('app.onedrive.run_onedrive_poll')
    def test_onedrive_poll_route(self, mock_poll, client, mock_sync_lock):
        """Test OneDrive manual poll route."""
        # Mock poll result
        mock_poll.return_value = {
            "data": Mock(to_dict=Mock(return_value=[
                {"Job #": 123, "Release #": "456", "Job": "Test Job"}
            ]))
        }
        
        response = client.get('/onedrive/poll')
        assert response.status_code == 200
        
        mock_poll.assert_called_once()
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]["Job #"] == 123
