"""
Unit tests for OneDrive utility functions.

These tests focus on data parsing and transformation functions that are
pure functions without external dependencies.
"""
import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import patch, Mock

from app.onedrive.utils import parse_excel_datetime, parse_polling_data


class TestParseExcelDatetime:
    """Test Excel datetime parsing functionality."""
    
    @pytest.mark.unit
    def test_parse_valid_datetime_string(self):
        """Test parsing valid ISO datetime string."""
        dt_str = "2023-01-20T16:00:00.000Z"
        result = parse_excel_datetime(dt_str)
        
        expected = datetime(2023, 1, 20, 16, 0, 0)
        assert result == expected
        assert result.tzinfo is None  # Should be naive
    
    @pytest.mark.unit
    def test_parse_datetime_with_offset(self):
        """Test parsing datetime with timezone offset."""
        dt_str = "2023-01-20T16:00:00.000+00:00"
        result = parse_excel_datetime(dt_str)
        
        expected = datetime(2023, 1, 20, 16, 0, 0)
        assert result == expected
        assert result.tzinfo is None  # Should be naive
    
    @pytest.mark.unit
    def test_parse_none_datetime(self):
        """Test parsing None datetime."""
        result = parse_excel_datetime(None)
        assert result is None
    
    @pytest.mark.unit
    def test_parse_empty_datetime(self):
        """Test parsing empty datetime string."""
        result = parse_excel_datetime("")
        assert result is None


class TestParsePollingData:
    """Test OneDrive polling data parsing."""
    
    @pytest.mark.unit
    @patch('app.onedrive.utils.get_excel_data_with_timestamp')
    def test_parse_valid_polling_data(self, mock_get_data):
        """Test parsing valid polling data."""
        sample_df = pd.DataFrame([{
            "Job #": 123,
            "Release #": "V456",
            "Job": "Test Job"
        }])
        
        mock_get_data.return_value = {
            "last_modified_time": "2023-01-20T16:00:00.000Z",
            "data": sample_df
        }
        
        result = parse_polling_data()
        
        assert result is not None
        assert result["last_modified_time"] == "2023-01-20T16:00:00.000Z"
        assert isinstance(result["data"], pd.DataFrame)
        assert len(result["data"]) == 1
    
    @pytest.mark.unit
    @patch('app.onedrive.utils.get_excel_data_with_timestamp')
    def test_parse_none_data(self, mock_get_data):
        """Test parsing when API returns None."""
        mock_get_data.return_value = None
        
        result = parse_polling_data()
        assert result is None
    
    @pytest.mark.unit
    @patch('app.onedrive.utils.get_excel_data_with_timestamp')
    def test_parse_invalid_format(self, mock_get_data):
        """Test parsing invalid data format."""
        mock_get_data.return_value = {"invalid": "format"}
        
        result = parse_polling_data()
        assert result is None
    
    @pytest.mark.unit
    @patch('app.onedrive.utils.get_excel_data_with_timestamp')
    def test_parse_missing_data_field(self, mock_get_data):
        """Test parsing with missing data field."""
        mock_get_data.return_value = {
            "last_modified_time": "2023-01-20T16:00:00.000Z"
            # Missing "data" field
        }
        
        result = parse_polling_data()
        assert result is None
    
    @pytest.mark.unit
    @patch('app.onedrive.utils.get_excel_data_with_timestamp')
    def test_parse_missing_timestamp_field(self, mock_get_data):
        """Test parsing with missing timestamp field."""
        sample_df = pd.DataFrame([{"Job #": 123}])
        mock_get_data.return_value = {
            "data": sample_df
            # Missing "last_modified_time" field
        }
        
        result = parse_polling_data()
        assert result is None
