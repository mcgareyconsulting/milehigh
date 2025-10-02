"""
Unit tests for Trello utilities.
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


@pytest.mark.unit
@pytest.mark.trello
class TestParseWebhookData:
    """Test webhook data parsing."""
    
    def test_parse_card_moved_webhook(self):
        """Test parsing a card moved webhook."""
        data = {
            "action": {
                "type": "updateCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "card123",
                        "name": "Test Card"
                    },
                    "listBefore": {"name": "To Do"},
                    "listAfter": {"name": "In Progress"}
                }
            }
        }
        
        result = parse_webhook_data(data)
        
        assert result["event"] == "card_moved"
        assert result["handled"] is True
        assert result["card_id"] == "card123"
        assert result["card_name"] == "Test Card"
        assert result["from"] == "To Do"
        assert result["to"] == "In Progress"
        assert result["time"] == "2024-01-15T12:30:00.000Z"
    
    def test_parse_card_updated_webhook(self):
        """Test parsing a card field update webhook."""
        data = {
            "action": {
                "type": "updateCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "card123",
                        "name": "Updated Card"
                    },
                    "old": {
                        "name": "Old Card Name",
                        "desc": "Old description"
                    }
                }
            }
        }
        
        result = parse_webhook_data(data)
        
        assert result["event"] == "card_updated"
        assert result["handled"] is True
        assert result["card_id"] == "card123"
        assert result["card_name"] == "Updated Card"
        assert "name" in result["changed_fields"]
        assert "desc" in result["changed_fields"]
    
    def test_parse_card_updated_with_labels(self):
        """Test parsing card update with label changes."""
        data = {
            "action": {
                "type": "updateCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "card123",
                        "name": "Card with Labels"
                    },
                    "label": {"name": "Priority"}
                }
            }
        }
        
        result = parse_webhook_data(data)
        
        assert result["event"] == "card_updated"
        assert result["handled"] is True
        assert "labels" in result["changed_fields"]
    
    def test_parse_position_only_update(self):
        """Test that position-only updates are ignored."""
        data = {
            "action": {
                "type": "updateCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "card123",
                        "name": "Test Card"
                    },
                    "old": {
                        "pos": 12345
                    }
                }
            }
        }
        
        result = parse_webhook_data(data)
        
        assert result["event"] == "unhandled"
        assert result["handled"] is False
    
    def test_parse_unhandled_webhook(self):
        """Test parsing an unhandled webhook type."""
        data = {
            "action": {
                "type": "createCard",
                "date": "2024-01-15T12:30:00.000Z",
                "data": {
                    "card": {
                        "id": "card123",
                        "name": "New Card"
                    }
                }
            }
        }
        
        result = parse_webhook_data(data)
        
        assert result["event"] == "unhandled"
        assert result["handled"] is False
        assert result["details"] == data
    
    def test_parse_webhook_error_handling(self):
        """Test error handling in webhook parsing."""
        invalid_data = {"invalid": "data"}
        
        result = parse_webhook_data(invalid_data)
        
        assert result["event"] == "error"
        assert result["handled"] is False
        assert "error" in result


@pytest.mark.unit
@pytest.mark.trello
class TestParseTrelloDatetime:
    """Test Trello datetime parsing."""
    
    def test_parse_utc_datetime(self):
        """Test parsing UTC datetime with Z suffix."""
        dt_str = "2024-01-15T12:30:00.000Z"
        result = parse_trello_datetime(dt_str)
        
        expected = datetime(2024, 1, 15, 12, 30, 0)
        assert result == expected
        assert result.tzinfo is None  # Should be naive
    
    def test_parse_datetime_without_z(self):
        """Test parsing datetime without Z suffix."""
        dt_str = "2024-01-15T12:30:00.000"
        result = parse_trello_datetime(dt_str)
        
        expected = datetime(2024, 1, 15, 12, 30, 0)
        assert result == expected
        assert result.tzinfo is None
    
    def test_parse_datetime_with_timezone(self):
        """Test parsing datetime with timezone offset."""
        dt_str = "2024-01-15T12:30:00.000-07:00"
        result = parse_trello_datetime(dt_str)
        
        expected = datetime(2024, 1, 15, 12, 30, 0)
        assert result == expected
        assert result.tzinfo is None
    
    def test_parse_none_datetime(self):
        """Test parsing None datetime."""
        result = parse_trello_datetime(None)
        assert result is None
    
    def test_parse_empty_datetime(self):
        """Test parsing empty datetime."""
        result = parse_trello_datetime("")
        assert result is None


@pytest.mark.unit
@pytest.mark.trello
class TestExtractCardName:
    """Test card name extraction from webhook data."""
    
    def test_extract_card_name_success(self):
        """Test successful card name extraction."""
        data = {
            "action": {
                "display": {
                    "entities": {
                        "card": {
                            "text": "Test Card Name"
                        }
                    }
                }
            }
        }
        
        result = extract_card_name(data)
        assert result == "Test Card Name"
    
    def test_extract_card_name_missing_data(self):
        """Test card name extraction with missing data."""
        data = {"action": {}}
        
        result = extract_card_name(data)
        assert result is None
    
    def test_extract_card_name_none_input(self):
        """Test card name extraction with None input."""
        result = extract_card_name(None)
        assert result is None


@pytest.mark.unit
@pytest.mark.trello
class TestExtractIdentifier:
    """Test identifier extraction from card names."""
    
    def test_extract_standard_identifier(self):
        """Test extracting standard 123-456 identifier."""
        card_name = "123-456 Test Job Name"
        result = extract_identifier(card_name)
        assert result == "123-456"
    
    def test_extract_v_identifier(self):
        """Test extracting 123-V456 identifier."""
        card_name = "123-V456 Another Job"
        result = extract_identifier(card_name)
        assert result == "123-V456"
    
    def test_extract_identifier_case_insensitive(self):
        """Test case insensitive identifier extraction."""
        card_name = "123-v456 Lowercase V"
        result = extract_identifier(card_name)
        assert result == "123-v456"
    
    def test_extract_identifier_at_start_only(self):
        """Test that identifier must be at the start."""
        card_name = "Some text 123-456 in middle"
        result = extract_identifier(card_name)
        assert result is None
    
    def test_extract_identifier_none_input(self):
        """Test identifier extraction with None input."""
        result = extract_identifier(None)
        assert result is None
    
    def test_extract_identifier_empty_input(self):
        """Test identifier extraction with empty input."""
        result = extract_identifier("")
        assert result is None
    
    def test_extract_identifier_no_match(self):
        """Test identifier extraction with no matching pattern."""
        card_name = "No identifier here"
        result = extract_identifier(card_name)
        assert result is None
    
    def test_extract_identifier_wrong_format(self):
        """Test identifier extraction with wrong format."""
        card_name = "12-456 Too short"
        result = extract_identifier(card_name)
        assert result is None
        
        card_name = "1234-456 Too long"
        result = extract_identifier(card_name)
        assert result is None


@pytest.mark.unit
@pytest.mark.trello
class TestMountainDueDatetime:
    """Test Mountain timezone due date conversion."""
    
    def test_mountain_due_datetime_with_date(self):
        """Test converting date to Mountain 6pm."""
        test_date = date(2024, 7, 15)  # Summer date (DST)
        result = mountain_due_datetime(test_date)
        
        # Should be 6pm Mountain time converted to UTC
        # During DST, Mountain time is UTC-6, so 6pm Mountain = 12am UTC next day
        assert result.endswith("Z")
        assert "2024-07-16T00:00:00" in result
    
    def test_mountain_due_datetime_with_datetime(self):
        """Test converting datetime to Mountain 6pm (uses date part only)."""
        test_datetime = datetime(2024, 1, 15, 10, 30)  # Winter date (no DST)
        result = mountain_due_datetime(test_datetime)
        
        # Should use date part only and convert 6pm Mountain to UTC
        # During winter, Mountain time is UTC-7, so 6pm Mountain = 1am UTC next day
        assert result.endswith("Z")
        assert "2024-01-16T01:00:00" in result
    
    def test_mountain_due_datetime_winter_vs_summer(self):
        """Test DST handling in Mountain timezone."""
        winter_date = date(2024, 1, 15)  # Standard time
        summer_date = date(2024, 7, 15)  # Daylight time
        
        winter_result = mountain_due_datetime(winter_date)
        summer_result = mountain_due_datetime(summer_date)
        
        # Winter: MST (UTC-7), so 6pm = 1am UTC next day
        # Summer: MDT (UTC-6), so 6pm = 12am UTC next day
        assert "01:00:00" in winter_result
        assert "00:00:00" in summer_result
