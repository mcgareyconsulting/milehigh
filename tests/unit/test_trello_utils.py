"""
Unit tests for Trello utility functions.

These tests focus on data parsing and transformation functions that are
pure functions without external dependencies.
"""
import pytest
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

from app.trello.utils import (
    parse_webhook_data,
    parse_trello_datetime,
    extract_card_name,
    extract_identifier,
    mountain_due_datetime
)


class TestParseWebhookData:
    """Test webhook data parsing functionality."""
    
    @pytest.mark.unit
    def test_parse_card_moved_webhook(self):
        """Test parsing of card movement webhook data."""
        webhook_data = {
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
        
        result = parse_webhook_data(webhook_data)
        
        assert result["event"] == "card_moved"
        assert result["handled"] is True
        assert result["card_id"] == "test_card_123"
        assert result["card_name"] == "123-V456 Test Job"
        assert result["from"] == "In Progress"
        assert result["to"] == "Paint complete"
        assert result["time"] == "2023-01-20T15:30:00.000Z"
    
    @pytest.mark.unit
    def test_parse_card_updated_webhook(self):
        """Test parsing of card update webhook data."""
        webhook_data = {
            "action": {
                "type": "updateCard",
                "date": "2023-01-20T15:30:00.000Z",
                "data": {
                    "card": {
                        "id": "test_card_123",
                        "name": "123-V456 Updated Name"
                    },
                    "old": {
                        "name": "123-V456 Old Name"
                    }
                }
            }
        }
        
        result = parse_webhook_data(webhook_data)
        
        assert result["event"] == "card_updated"
        assert result["handled"] is True
        assert result["card_id"] == "test_card_123"
        assert result["card_name"] == "123-V456 Updated Name"
        assert "name" in result["changed_fields"]
    
    @pytest.mark.unit
    def test_parse_unhandled_webhook(self):
        """Test parsing of unhandled webhook data."""
        webhook_data = {
            "action": {
                "type": "deleteCard",
                "date": "2023-01-20T15:30:00.000Z",
                "data": {
                    "card": {
                        "id": "test_card_123",
                        "name": "Test Card"
                    }
                }
            }
        }
        
        result = parse_webhook_data(webhook_data)
        
        assert result["event"] == "unhandled"
        assert result["handled"] is False
        assert "details" in result
    
    @pytest.mark.unit
    def test_parse_malformed_webhook(self):
        """Test parsing of malformed webhook data."""
        webhook_data = {"invalid": "data"}
        
        result = parse_webhook_data(webhook_data)
        
        assert result["event"] == "error"
        assert result["handled"] is False
        assert "error" in result
    
    @pytest.mark.unit
    def test_skip_position_only_changes(self):
        """Test that position-only changes are ignored."""
        webhook_data = {
            "action": {
                "type": "updateCard",
                "date": "2023-01-20T15:30:00.000Z",
                "data": {
                    "card": {
                        "id": "test_card_123",
                        "name": "Test Card"
                    },
                    "old": {
                        "pos": 12345
                    }
                }
            }
        }
        
        result = parse_webhook_data(webhook_data)
        
        assert result["event"] == "unhandled"
        assert result["handled"] is False


class TestParseTrelloDatetime:
    """Test Trello datetime parsing functionality."""
    
    @pytest.mark.unit
    def test_parse_utc_datetime_with_z(self):
        """Test parsing UTC datetime with Z suffix."""
        dt_str = "2023-01-20T15:30:00.000Z"
        result = parse_trello_datetime(dt_str)
        
        expected = datetime(2023, 1, 20, 15, 30, 0)
        assert result == expected
        assert result.tzinfo is None  # Should be naive
    
    @pytest.mark.unit
    def test_parse_datetime_with_offset(self):
        """Test parsing datetime with timezone offset."""
        dt_str = "2023-01-20T15:30:00.000+00:00"
        result = parse_trello_datetime(dt_str)
        
        expected = datetime(2023, 1, 20, 15, 30, 0)
        assert result == expected
        assert result.tzinfo is None  # Should be naive
    
    @pytest.mark.unit
    def test_parse_none_datetime(self):
        """Test parsing None datetime."""
        result = parse_trello_datetime(None)
        assert result is None
    
    @pytest.mark.unit
    def test_parse_empty_datetime(self):
        """Test parsing empty datetime string."""
        result = parse_trello_datetime("")
        assert result is None


class TestExtractCardName:
    """Test card name extraction from webhook data."""
    
    @pytest.mark.unit
    def test_extract_valid_card_name(self):
        """Test extracting valid card name."""
        data = {
            "action": {
                "display": {
                    "entities": {
                        "card": {
                            "text": "123-V456 Test Job"
                        }
                    }
                }
            }
        }
        
        result = extract_card_name(data)
        assert result == "123-V456 Test Job"
    
    @pytest.mark.unit
    def test_extract_missing_card_name(self):
        """Test extracting from data without card name."""
        data = {"action": {"display": {}}}
        
        result = extract_card_name(data)
        assert result is None
    
    @pytest.mark.unit
    def test_extract_malformed_data(self):
        """Test extracting from malformed data."""
        data = {"invalid": "structure"}
        
        result = extract_card_name(data)
        assert result is None


class TestExtractIdentifier:
    """Test identifier extraction from card names."""
    
    @pytest.mark.unit
    def test_extract_numeric_identifier(self):
        """Test extracting numeric identifier (123-456)."""
        card_name = "123-456 Some Job Name"
        result = extract_identifier(card_name)
        assert result == "123-456"
    
    @pytest.mark.unit
    def test_extract_version_identifier(self):
        """Test extracting version identifier (123-V456)."""
        card_name = "123-V456 Some Job Name"
        result = extract_identifier(card_name)
        assert result == "123-V456"
    
    @pytest.mark.unit
    def test_extract_case_insensitive(self):
        """Test extracting identifier case insensitive."""
        card_name = "123-v456 Some Job Name"
        result = extract_identifier(card_name)
        assert result == "123-v456"
    
    @pytest.mark.unit
    def test_extract_no_identifier(self):
        """Test extracting from card name without identifier."""
        card_name = "Some Job Name Without Identifier"
        result = extract_identifier(card_name)
        assert result is None
    
    @pytest.mark.unit
    def test_extract_identifier_not_at_start(self):
        """Test that identifiers not at start are ignored."""
        card_name = "Some Job 123-456 Name"
        result = extract_identifier(card_name)
        assert result is None
    
    @pytest.mark.unit
    def test_extract_none_card_name(self):
        """Test extracting from None card name."""
        result = extract_identifier(None)
        assert result is None
    
    @pytest.mark.unit
    def test_extract_empty_card_name(self):
        """Test extracting from empty card name."""
        result = extract_identifier("")
        assert result is None


class TestMountainDueDateTime:
    """Test Mountain time due date conversion."""
    
    @pytest.mark.unit
    def test_date_to_mountain_due_datetime(self):
        """Test converting date to Mountain 6pm UTC."""
        local_date = date(2023, 6, 15)  # Summer (MDT)
        result = mountain_due_datetime(local_date)
        
        # 6pm MDT = 8pm MST = 1am UTC next day (summer)
        # 6pm MST = 1am UTC next day (winter)
        # June 15 would be MDT (UTC-6), so 6pm MDT = midnight UTC
        assert result.endswith("Z")
        assert "2023-06-16T00:00:00" in result
    
    @pytest.mark.unit
    def test_datetime_to_mountain_due_datetime(self):
        """Test converting datetime to Mountain 6pm UTC."""
        local_datetime = datetime(2023, 6, 15, 10, 30)  # Time should be ignored
        result = mountain_due_datetime(local_datetime)
        
        assert result.endswith("Z")
        assert "2023-06-16T00:00:00" in result
    
    @pytest.mark.unit
    def test_winter_date_conversion(self):
        """Test converting winter date (MST instead of MDT)."""
        local_date = date(2023, 12, 15)  # Winter (MST)
        result = mountain_due_datetime(local_date)
        
        # 6pm MST = UTC+7 = 1am UTC next day
        assert result.endswith("Z")
        assert "2023-12-16T01:00:00" in result
