"""
Sample data fixtures for testing.
"""
from datetime import datetime, date
import pandas as pd


class SampleTrelloData:
    """Sample Trello API data for testing."""
    
    @staticmethod
    def webhook_card_moved():
        """Sample webhook data for card moved event."""
        return {
            "action": {
                "type": "updateCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "card_123",
                        "name": "123-456 Test Job"
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
    
    @staticmethod
    def webhook_card_updated():
        """Sample webhook data for card field update."""
        return {
            "action": {
                "type": "updateCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "card_456",
                        "name": "124-457 Updated Job"
                    },
                    "old": {
                        "name": "124-457 Old Job Name",
                        "desc": "Old description",
                        "due": "2024-01-01T18:00:00.000Z"
                    }
                }
            }
        }
    
    @staticmethod
    def card_api_response():
        """Sample Trello card API response."""
        return {
            "id": "card_789",
            "name": "125-458 API Test Job",
            "desc": "Test card from API",
            "idList": "list_789",
            "due": "2024-02-15T18:00:00.000Z",
            "labels": [
                {"id": "label_1", "name": "Priority"},
                {"id": "label_2", "name": "Urgent"}
            ],
            "url": "https://trello.com/c/card_789",
            "shortUrl": "https://trello.com/c/shorturl"
        }
    
    @staticmethod
    def lists_api_response():
        """Sample Trello lists API response."""
        return [
            {"id": "list_1", "name": "Backlog", "closed": False},
            {"id": "list_2", "name": "In Progress", "closed": False},
            {"id": "list_3", "name": "Fit Up Complete.", "closed": False},
            {"id": "list_4", "name": "Paint complete", "closed": False},
            {"id": "list_5", "name": "Shipping completed", "closed": False},
            {"id": "list_6", "name": "Archive", "closed": True}
        ]
    
    @staticmethod
    def cards_subset_response():
        """Sample response for cards from target lists."""
        return [
            {
                "id": "card_fitup_1",
                "name": "123-456 Fitup Job",
                "desc": "Job in fitup stage",
                "idList": "list_3",
                "due": "2024-02-01T18:00:00.000Z",
                "labels": []
            },
            {
                "id": "card_paint_1",
                "name": "124-457 Paint Job",
                "desc": "Job in paint stage",
                "idList": "list_4",
                "due": "2024-02-05T18:00:00.000Z",
                "labels": [{"name": "Priority"}]
            },
            {
                "id": "card_ship_1",
                "name": "125-458 Shipping Job",
                "desc": "Job ready to ship",
                "idList": "list_5",
                "due": None,
                "labels": [{"name": "Complete"}]
            }
        ]


class SampleOneDriveData:
    """Sample OneDrive/Excel data for testing."""
    
    @staticmethod
    def access_token_response():
        """Sample OAuth token response."""
        return {
            "token_type": "Bearer",
            "expires_in": 3600,
            "ext_expires_in": 3600,
            "access_token": "sample_access_token_12345"
        }
    
    @staticmethod
    def file_metadata_response():
        """Sample file metadata response."""
        return {
            "id": "file_123",
            "name": "Job Log 2.4 Test.xlsm",
            "size": 1048576,
            "lastModifiedDateTime": "2024-01-15T12:30:00.000Z",
            "lastModifiedBy": {
                "user": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                }
            }
        }
    
    @staticmethod
    def excel_dataframe_small():
        """Small sample Excel DataFrame for testing."""
        return pd.DataFrame({
            "Job #": [123, 124, 125],
            "Release #": [456, 457, 458],
            "Job": ["Test Job 1", "Test Job 2", "Test Job 3"],
            "Description": ["First test job", "Second test job", "Third test job"],
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
    
    @staticmethod
    def excel_dataframe_large():
        """Larger sample Excel DataFrame for testing."""
        jobs = []
        for i in range(100, 200):  # 100 jobs
            jobs.append({
                "Job #": i,
                "Release #": f"{i+300}",
                "Job": f"Job {i}",
                "Description": f"Description for job {i}",
                "Fab Hrs": float(i % 20 + 5),
                "Install HRS": float(i % 15 + 3),
                "Paint color": ["Blue", "Red", "Green", "Yellow", "Black"][i % 5],
                "PM": ["John", "Jane", "Bob", "Alice"][i % 4],
                "BY": ["Charlie", "Dave", "Eve", "Frank"][i % 4],
                "Released": date(2024, 1, (i % 28) + 1),
                "Fab Order": float(i % 10),
                "Cut start": ["X", "O", ""][i % 3],
                "Fitup comp": ["X", "O", ""][i % 3],
                "Welded": ["X", "O", ""][i % 3],
                "Paint Comp": ["X", "O", ""][i % 3],
                "Ship": ["X", "O", "T", ""][i % 4],
                "Start install": date(2024, 2, (i % 28) + 1),
                "Comp. ETA": date(2024, 3, (i % 28) + 1),
                "Job Comp": ["X", ""][i % 2],
                "Invoiced": ["X", ""][i % 2],
                "Notes": f"Notes for job {i}",
                "start_install_formula": ["", "=TODAY()+7"][i % 2],
                "start_install_formulaTF": [False, True][i % 2]
            })
        
        return pd.DataFrame(jobs)
    
    @staticmethod
    def polling_data_response():
        """Sample polling data response structure."""
        return {
            "last_modified_time": "2024-01-15T12:30:00.000Z",
            "data": SampleOneDriveData.excel_dataframe_small()
        }
    
    @staticmethod
    def cell_update_success_response():
        """Sample successful cell update response."""
        return {
            "address": "M15",
            "values": [["X"]],
            "numberFormat": [["General"]],
            "formulas": [["X"]],
            "formulasLocal": [["X"]]
        }


class SampleDatabaseData:
    """Sample database records for testing."""
    
    @staticmethod
    def job_records():
        """Sample Job records."""
        from app.models import Job
        
        return [
            Job(
                job=123,
                release="456",
                job_name="Database Test Job 1",
                description="First test job from database",
                fab_hrs=15.0,
                install_hrs=12.0,
                paint_color="Blue",
                pm="John",
                by="Alice",
                released=date(2024, 1, 15),
                fab_order=1.0,
                cut_start="X",
                fitup_comp="X",
                welded="O",
                paint_comp="",
                ship="",
                start_install=date(2024, 2, 1),
                comp_eta=date(2024, 2, 15),
                job_comp="",
                invoiced="",
                notes="Test notes 1",
                trello_card_id="db_card_123",
                trello_card_name="123-456 Database Test Job 1",
                trello_list_id="db_list_123",
                trello_list_name="In Progress",
                trello_card_description="Test card from database",
                trello_card_date=date(2024, 2, 1),
                last_updated_at=datetime(2024, 1, 10, 12, 0, 0),
                source_of_update="Excel"
            ),
            Job(
                job=124,
                release="457",
                job_name="Database Test Job 2",
                description="Second test job from database",
                fab_hrs=18.0,
                install_hrs=14.0,
                paint_color="Red",
                pm="Jane",
                by="Bob",
                released=date(2024, 1, 16),
                fab_order=2.0,
                cut_start="X",
                fitup_comp="X",
                welded="X",
                paint_comp="X",
                ship="O",
                start_install=date(2024, 2, 2),
                comp_eta=date(2024, 2, 16),
                job_comp="",
                invoiced="",
                notes="Test notes 2",
                trello_card_id="db_card_124",
                trello_card_name="124-457 Database Test Job 2",
                trello_list_id="db_list_124",
                trello_list_name="Paint complete",
                trello_card_description="Second test card",
                trello_card_date=date(2024, 2, 2),
                last_updated_at=datetime(2024, 1, 11, 13, 0, 0),
                source_of_update="Trello"
            )
        ]
    
    @staticmethod
    def sync_operations():
        """Sample SyncOperation records."""
        from app.models import SyncOperation, SyncStatus
        
        return [
            SyncOperation(
                operation_id="sync_op_1",
                operation_type="trello_webhook",
                status=SyncStatus.COMPLETED,
                started_at=datetime(2024, 1, 15, 12, 0, 0),
                completed_at=datetime(2024, 1, 15, 12, 0, 5),
                duration_seconds=5.0,
                source_system="trello",
                source_id="card_123",
                records_processed=1,
                records_updated=1,
                records_created=0,
                records_failed=0
            ),
            SyncOperation(
                operation_id="sync_op_2",
                operation_type="onedrive_poll",
                status=SyncStatus.FAILED,
                started_at=datetime(2024, 1, 15, 13, 0, 0),
                completed_at=datetime(2024, 1, 15, 13, 0, 10),
                duration_seconds=10.0,
                source_system="onedrive",
                source_id=None,
                records_processed=5,
                records_updated=0,
                records_created=0,
                records_failed=5,
                error_type="APIError",
                error_message="Failed to connect to OneDrive API"
            ),
            SyncOperation(
                operation_id="sync_op_3",
                operation_type="trello_webhook",
                status=SyncStatus.IN_PROGRESS,
                started_at=datetime(2024, 1, 15, 14, 0, 0),
                source_system="trello",
                source_id="card_456",
                records_processed=0,
                records_updated=0,
                records_created=0,
                records_failed=0
            )
        ]
    
    @staticmethod
    def sync_logs():
        """Sample SyncLog records."""
        from app.models import SyncLog
        
        return [
            SyncLog(
                operation_id="sync_op_1",
                level="INFO",
                message="Sync operation started",
                timestamp=datetime(2024, 1, 15, 12, 0, 0),
                job_id=1,
                trello_card_id="card_123",
                excel_identifier="123-456",
                data={"event": "card_moved", "from": "In Progress", "to": "Paint complete"}
            ),
            SyncLog(
                operation_id="sync_op_1",
                level="INFO",
                message="Job status updated",
                timestamp=datetime(2024, 1, 15, 12, 0, 2),
                job_id=1,
                trello_card_id="card_123",
                excel_identifier="123-456",
                data={"field": "paint_comp", "old_value": "", "new_value": "X"}
            ),
            SyncLog(
                operation_id="sync_op_1",
                level="INFO",
                message="Excel cell updated",
                timestamp=datetime(2024, 1, 15, 12, 0, 4),
                job_id=1,
                trello_card_id="card_123",
                excel_identifier="123-456",
                data={"cell": "O15", "value": "X"}
            ),
            SyncLog(
                operation_id="sync_op_2",
                level="ERROR",
                message="OneDrive API connection failed",
                timestamp=datetime(2024, 1, 15, 13, 0, 5),
                data={"error_type": "ConnectionError", "status_code": 500}
            )
        ]


class SampleCombinedData:
    """Sample combined Trello-Excel data for testing."""
    
    @staticmethod
    def combined_data_matched():
        """Sample data where Trello and Excel records match."""
        return [
            {
                "identifier": "123-456",
                "trello": {
                    "id": "trello_card_123",
                    "name": "123-456 Matched Job",
                    "desc": "Job that exists in both systems",
                    "list_id": "list_progress",
                    "list_name": "In Progress",
                    "due": "2024-02-01T18:00:00.000Z",
                    "labels": ["Priority"]
                },
                "excel": {
                    "Job #": 123,
                    "Release #": "456",
                    "Job": "Matched Job",
                    "Description": "Job that exists in both systems",
                    "Fitup comp": "X",
                    "Welded": "O",
                    "Paint Comp": "",
                    "Ship": "",
                    "Start install": date(2024, 2, 1)
                }
            },
            {
                "identifier": "124-457",
                "trello": {
                    "id": "trello_card_124",
                    "name": "124-457 Another Matched Job",
                    "desc": "Another job in both systems",
                    "list_id": "list_paint",
                    "list_name": "Paint complete",
                    "due": "2024-02-05T18:00:00.000Z",
                    "labels": []
                },
                "excel": {
                    "Job #": 124,
                    "Release #": "457",
                    "Job": "Another Matched Job",
                    "Description": "Another job in both systems",
                    "Fitup comp": "X",
                    "Welded": "X",
                    "Paint Comp": "X",
                    "Ship": "O",
                    "Start install": date(2024, 2, 5)
                }
            }
        ]
    
    @staticmethod
    def combined_data_trello_only():
        """Sample data for jobs that exist only in Trello."""
        return [
            {
                "identifier": "999-888",
                "trello": {
                    "id": "trello_only_card",
                    "name": "999-888 Trello Only Job",
                    "desc": "This job only exists in Trello",
                    "list_id": "list_backlog",
                    "list_name": "Backlog",
                    "due": None,
                    "labels": ["New"]
                },
                "excel": None
            }
        ]
    
    @staticmethod
    def combined_data_excel_only():
        """Sample data for jobs that exist only in Excel."""
        return [
            {
                "identifier": "777-666",
                "trello": None,
                "excel": {
                    "Job #": 777,
                    "Release #": "666",
                    "Job": "Excel Only Job",
                    "Description": "This job only exists in Excel",
                    "Fitup comp": "",
                    "Welded": "",
                    "Paint Comp": "",
                    "Ship": "",
                    "Start install": date(2024, 3, 1)
                }
            }
        ]
