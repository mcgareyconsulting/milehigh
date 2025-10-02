"""
Test helper functions and utilities.
"""
import json
from datetime import datetime, date
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock
import pandas as pd
from app.models import db, Job, SyncOperation, SyncLog


class DatabaseHelper:
    """Helper class for database operations in tests."""
    
    @staticmethod
    def create_job(app_context, **kwargs):
        """Create and save a Job record with default values."""
        defaults = {
            'job': 123,
            'release': '456',
            'job_name': 'Test Job',
            'description': 'Test job description',
            'fab_hrs': 10.0,
            'install_hrs': 8.0,
            'paint_color': 'Blue',
            'pm': 'John',
            'by': 'Jane',
            'released': date(2024, 1, 15),
            'fab_order': 1.0,
            'cut_start': 'X',
            'fitup_comp': 'O',
            'welded': '',
            'paint_comp': '',
            'ship': '',
            'start_install': date(2024, 2, 1),
            'comp_eta': date(2024, 2, 15),
            'job_comp': '',
            'invoiced': '',
            'notes': 'Test notes',
            'last_updated_at': datetime(2024, 1, 10, 12, 0, 0),
            'source_of_update': 'Excel'
        }
        
        defaults.update(kwargs)
        job = Job(**defaults)
        
        with app_context:
            db.session.add(job)
            db.session.commit()
            # Refresh to get the ID
            db.session.refresh(job)
        
        return job
    
    @staticmethod
    def create_sync_operation(app_context, **kwargs):
        """Create and save a SyncOperation record with default values."""
        from app.models import SyncStatus
        
        defaults = {
            'operation_id': 'test_op_123',
            'operation_type': 'test_operation',
            'status': SyncStatus.PENDING,
            'source_system': 'test',
            'source_id': 'test_id'
        }
        
        defaults.update(kwargs)
        operation = SyncOperation(**defaults)
        
        with app_context:
            db.session.add(operation)
            db.session.commit()
            db.session.refresh(operation)
        
        return operation
    
    @staticmethod
    def create_sync_log(app_context, **kwargs):
        """Create and save a SyncLog record with default values."""
        defaults = {
            'operation_id': 'test_op_123',
            'level': 'INFO',
            'message': 'Test log message',
            'timestamp': datetime(2024, 1, 15, 12, 0, 0)
        }
        
        defaults.update(kwargs)
        log = SyncLog(**defaults)
        
        with app_context:
            db.session.add(log)
            db.session.commit()
            db.session.refresh(log)
        
        return log
    
    @staticmethod
    def clear_all_tables(app_context):
        """Clear all database tables."""
        with app_context:
            db.session.query(SyncLog).delete()
            db.session.query(SyncOperation).delete()
            db.session.query(Job).delete()
            db.session.commit()


class MockHelper:
    """Helper class for creating mock objects."""
    
    @staticmethod
    def create_mock_requests_response(status_code=200, json_data=None, text="OK"):
        """Create a mock requests response object."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.text = text
        mock_response.json.return_value = json_data or {}
        mock_response.raise_for_status.return_value = None
        
        if status_code >= 400:
            from requests.exceptions import HTTPError
            mock_response.raise_for_status.side_effect = HTTPError(f"{status_code} Error")
        
        return mock_response
    
    @staticmethod
    def create_mock_trello_api():
        """Create mock Trello API responses."""
        mocks = {}
        
        # Mock card response
        mocks['get_card'] = Mock(return_value={
            "id": "mock_card_123",
            "name": "123-456 Mock Job",
            "desc": "Mock card description",
            "idList": "mock_list_123",
            "due": "2024-02-01T18:00:00.000Z",
            "labels": []
        })
        
        # Mock list name response
        mocks['get_list_name'] = Mock(return_value="Mock List")
        
        # Mock list by name response
        mocks['get_list_by_name'] = Mock(return_value={
            "id": "mock_list_123",
            "name": "Mock List"
        })
        
        # Mock update card response
        mocks['update_card'] = Mock(return_value={"success": True})
        
        return mocks
    
    @staticmethod
    def create_mock_onedrive_api():
        """Create mock OneDrive API responses."""
        mocks = {}
        
        # Mock access token
        mocks['get_token'] = Mock(return_value="mock_access_token")
        
        # Mock file metadata
        mocks['get_metadata'] = Mock(return_value={
            "name": "mock_file.xlsx",
            "lastModifiedDateTime": "2024-01-15T12:30:00.000Z",
            "size": 1024
        })
        
        # Mock Excel dataframe
        mocks['get_dataframe'] = Mock(return_value=pd.DataFrame({
            "Job #": [123],
            "Release #": [456],
            "Job": ["Mock Job"],
            "Fitup comp": ["X"],
            "Welded": ["O"],
            "Paint Comp": [""],
            "Ship": [""]
        }))
        
        # Mock cell update
        mocks['update_cell'] = Mock(return_value=True)
        
        return mocks


class DataHelper:
    """Helper class for creating test data."""
    
    @staticmethod
    def create_excel_dataframe(num_rows=3, include_formulas=False):
        """Create a test Excel DataFrame."""
        data = {
            "Job #": list(range(100, 100 + num_rows)),
            "Release #": [str(400 + i) for i in range(num_rows)],
            "Job": [f"Test Job {i}" for i in range(num_rows)],
            "Description": [f"Description {i}" for i in range(num_rows)],
            "Fab Hrs": [10.0 + i for i in range(num_rows)],
            "Install HRS": [8.0 + i for i in range(num_rows)],
            "Paint color": ["Blue", "Red", "Green"][:num_rows],
            "PM": ["John", "Jane", "Bob"][:num_rows],
            "BY": ["Alice", "Charlie", "Dave"][:num_rows],
            "Released": [date(2024, 1, 15 + i) for i in range(num_rows)],
            "Fab Order": [float(i + 1) for i in range(num_rows)],
            "Cut start": ["X", "O", ""][:num_rows],
            "Fitup comp": ["X", "O", ""][:num_rows],
            "Welded": ["O", "X", ""][:num_rows],
            "Paint Comp": ["", "X", ""][:num_rows],
            "Ship": ["", "O", ""][:num_rows],
            "Start install": [date(2024, 2, 1 + i) for i in range(num_rows)],
            "Comp. ETA": [date(2024, 2, 15 + i) for i in range(num_rows)],
            "Job Comp": [""] * num_rows,
            "Invoiced": [""] * num_rows,
            "Notes": [f"Note {i}" for i in range(num_rows)]
        }
        
        if include_formulas:
            data["start_install_formula"] = ["", "=TODAY()+7", ""][:num_rows]
            data["start_install_formulaTF"] = [False, True, False][:num_rows]
        else:
            data["start_install_formula"] = [""] * num_rows
            data["start_install_formulaTF"] = [False] * num_rows
        
        return pd.DataFrame(data)
    
    @staticmethod
    def create_trello_cards(num_cards=3):
        """Create a list of test Trello cards."""
        cards = []
        list_names = ["In Progress", "Paint complete", "Shipping completed"]
        
        for i in range(num_cards):
            cards.append({
                "id": f"card_{100 + i}",
                "name": f"{100 + i}-{400 + i} Test Card {i}",
                "desc": f"Test card description {i}",
                "idList": f"list_{i}",
                "list_name": list_names[i % len(list_names)],
                "due": f"2024-02-{(i % 28) + 1:02d}T18:00:00.000Z" if i % 2 else None,
                "labels": ["Priority"] if i % 3 == 0 else []
            })
        
        return cards
    
    @staticmethod
    def create_webhook_data(event_type="card_moved", **kwargs):
        """Create test webhook data."""
        defaults = {
            "card_id": "test_card_123",
            "card_name": "123-456 Test Job",
            "time": "2024-01-15T12:30:00.000Z"
        }
        defaults.update(kwargs)
        
        if event_type == "card_moved":
            return {
                "action": {
                    "type": "updateCard",
                    "date": defaults["time"],
                    "data": {
                        "card": {
                            "id": defaults["card_id"],
                            "name": defaults["card_name"]
                        },
                        "listBefore": {
                            "id": "list_before",
                            "name": defaults.get("from_list", "In Progress")
                        },
                        "listAfter": {
                            "id": "list_after",
                            "name": defaults.get("to_list", "Paint complete")
                        }
                    }
                }
            }
        elif event_type == "card_updated":
            return {
                "action": {
                    "type": "updateCard",
                    "date": defaults["time"],
                    "data": {
                        "card": {
                            "id": defaults["card_id"],
                            "name": defaults["card_name"]
                        },
                        "old": defaults.get("old_data", {
                            "name": "Old Card Name",
                            "desc": "Old description"
                        })
                    }
                }
            }
        
        return {}


class AssertionHelper:
    """Helper class for test assertions."""
    
    @staticmethod
    def assert_job_fields_equal(job1, job2, exclude_fields=None):
        """Assert that two Job objects have equal field values."""
        exclude_fields = exclude_fields or ['id', 'last_updated_at']
        
        for column in Job.__table__.columns:
            field_name = column.name
            if field_name not in exclude_fields:
                value1 = getattr(job1, field_name)
                value2 = getattr(job2, field_name)
                assert value1 == value2, f"Field {field_name} differs: {value1} != {value2}"
    
    @staticmethod
    def assert_sync_operation_completed(operation):
        """Assert that a sync operation completed successfully."""
        from app.models import SyncStatus
        
        assert operation.status == SyncStatus.COMPLETED
        assert operation.completed_at is not None
        assert operation.duration_seconds is not None
        assert operation.duration_seconds > 0
    
    @staticmethod
    def assert_sync_operation_failed(operation, error_type=None):
        """Assert that a sync operation failed."""
        from app.models import SyncStatus
        
        assert operation.status == SyncStatus.FAILED
        assert operation.error_message is not None
        
        if error_type:
            assert operation.error_type == error_type
    
    @staticmethod
    def assert_dataframe_equal(df1, df2, check_dtype=False):
        """Assert that two DataFrames are equal."""
        pd.testing.assert_frame_equal(df1, df2, check_dtype=check_dtype)
    
    @staticmethod
    def assert_dict_subset(subset_dict, full_dict):
        """Assert that subset_dict is a subset of full_dict."""
        for key, value in subset_dict.items():
            assert key in full_dict, f"Key '{key}' not found in full dictionary"
            assert full_dict[key] == value, f"Value mismatch for key '{key}': {full_dict[key]} != {value}"


class TimeHelper:
    """Helper class for time-related test utilities."""
    
    @staticmethod
    def create_datetime_sequence(start_time, count, interval_seconds=60):
        """Create a sequence of datetime objects."""
        from datetime import timedelta
        
        times = []
        current = start_time
        
        for _ in range(count):
            times.append(current)
            current += timedelta(seconds=interval_seconds)
        
        return times
    
    @staticmethod
    def create_date_sequence(start_date, count, interval_days=1):
        """Create a sequence of date objects."""
        from datetime import timedelta
        
        dates = []
        current = start_date
        
        for _ in range(count):
            dates.append(current)
            current += timedelta(days=interval_days)
        
        return dates
    
    @staticmethod
    def format_trello_datetime(dt):
        """Format datetime for Trello API format."""
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    @staticmethod
    def format_onedrive_datetime(dt):
        """Format datetime for OneDrive API format."""
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class ValidationHelper:
    """Helper class for validation utilities."""
    
    @staticmethod
    def is_valid_operation_id(operation_id):
        """Validate that operation_id follows expected format."""
        return isinstance(operation_id, str) and len(operation_id) == 8
    
    @staticmethod
    def is_valid_trello_card_id(card_id):
        """Validate Trello card ID format."""
        return isinstance(card_id, str) and len(card_id) > 0
    
    @staticmethod
    def is_valid_identifier(identifier):
        """Validate job identifier format (123-456 or 123-V456)."""
        import re
        pattern = r'^\d{3}-(?:\d{3}|V\d{3})$'
        return bool(re.match(pattern, identifier))
    
    @staticmethod
    def validate_sync_log_data(log_data):
        """Validate sync log data structure."""
        required_fields = ['operation_id', 'level', 'message']
        
        for field in required_fields:
            assert field in log_data, f"Required field '{field}' missing from log data"
        
        assert log_data['level'] in ['DEBUG', 'INFO', 'WARNING', 'ERROR']
        assert len(log_data['message']) > 0
    
    @staticmethod
    def validate_excel_cell_address(cell_address):
        """Validate Excel cell address format (e.g., 'A1', 'M15')."""
        import re
        pattern = r'^[A-Z]+\d+$'
        return bool(re.match(pattern, cell_address))
