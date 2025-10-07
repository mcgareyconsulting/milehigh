"""
Unit tests for sync helper functions.

These tests focus on the pure functions used in the sync process
that don't require database or external API calls.
"""
import pytest
import pandas as pd
from datetime import datetime, date
from unittest.mock import Mock

from app.sync import (
    compare_timestamps,
    as_date,
    determine_trello_list_from_db,
    is_formula_cell
)


class TestCompareTimestamps:
    """Test timestamp comparison functionality."""
    
    @pytest.mark.unit
    def test_compare_newer_timestamp(self):
        """Test comparing when event is newer than source."""
        event_time = datetime(2023, 1, 20, 16, 0, 0)
        source_time = datetime(2023, 1, 20, 15, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "newer"
    
    @pytest.mark.unit
    def test_compare_older_timestamp(self):
        """Test comparing when event is older than source."""
        event_time = datetime(2023, 1, 20, 14, 0, 0)
        source_time = datetime(2023, 1, 20, 15, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "older"
    
    @pytest.mark.unit
    def test_compare_equal_timestamp(self):
        """Test comparing when timestamps are equal."""
        event_time = datetime(2023, 1, 20, 15, 0, 0)
        source_time = datetime(2023, 1, 20, 15, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "older"
    
    @pytest.mark.unit
    def test_compare_none_event_time(self):
        """Test comparing when event time is None."""
        event_time = None
        source_time = datetime(2023, 1, 20, 15, 0, 0)
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result is None
    
    @pytest.mark.unit
    def test_compare_none_source_time(self):
        """Test comparing when source time is None."""
        event_time = datetime(2023, 1, 20, 16, 0, 0)
        source_time = None
        
        result = compare_timestamps(event_time, source_time, "test_op")
        assert result == "newer"


class TestAsDate:
    """Test date conversion functionality."""
    
    @pytest.mark.unit
    def test_convert_pandas_timestamp(self):
        """Test converting pandas Timestamp to date."""
        timestamp = pd.Timestamp("2023-01-20 15:30:00")
        result = as_date(timestamp)
        
        expected = date(2023, 1, 20)
        assert result == expected
    
    @pytest.mark.unit
    def test_convert_datetime(self):
        """Test converting datetime to date."""
        dt = datetime(2023, 1, 20, 15, 30, 0)
        result = as_date(dt)
        
        expected = date(2023, 1, 20)
        assert result == expected
    
    @pytest.mark.unit
    def test_convert_date(self):
        """Test converting date (should return same)."""
        d = date(2023, 1, 20)
        result = as_date(d)
        
        assert result == d
    
    @pytest.mark.unit
    def test_convert_string_date(self):
        """Test converting string date."""
        date_str = "2023-01-20"
        result = as_date(date_str)
        
        expected = date(2023, 1, 20)
        assert result == expected
    
    @pytest.mark.unit
    def test_convert_none(self):
        """Test converting None."""
        result = as_date(None)
        assert result is None
    
    @pytest.mark.unit
    def test_convert_pandas_na(self):
        """Test converting pandas NA."""
        result = as_date(pd.NA)
        assert result is None
    
    @pytest.mark.unit
    def test_convert_invalid_string(self):
        """Test converting invalid string."""
        result = as_date("invalid-date")
        assert result is None


class TestDetermineTrelloListFromDb:
    """Test Trello list determination from database status."""
    
    @pytest.mark.unit
    def test_determine_paint_complete_list(self):
        """Test determining Paint complete list."""
        # Mock job record
        rec = Mock()
        rec.fitup_comp = "X"
        rec.welded = "X"
        rec.paint_comp = "X"
        rec.ship = "O"
        
        result = determine_trello_list_from_db(rec)
        assert result == "Paint complete"
    
    @pytest.mark.unit
    def test_determine_paint_complete_list_with_t_ship(self):
        """Test determining Paint complete list with T ship status."""
        rec = Mock()
        rec.fitup_comp = "X"
        rec.welded = "X"
        rec.paint_comp = "X"
        rec.ship = "T"
        
        result = determine_trello_list_from_db(rec)
        assert result == "Paint complete"
    
    @pytest.mark.unit
    def test_determine_fitup_complete_list(self):
        """Test determining Fit Up Complete list."""
        rec = Mock()
        rec.fitup_comp = "X"
        rec.welded = "O"
        rec.paint_comp = None
        rec.ship = None
        
        result = determine_trello_list_from_db(rec)
        assert result == "Fit Up Complete."
    
    @pytest.mark.unit
    def test_determine_shipping_completed_list(self):
        """Test determining Shipping completed list."""
        rec = Mock()
        rec.fitup_comp = "X"
        rec.welded = "X"
        rec.paint_comp = "X"
        rec.ship = "X"
        
        result = determine_trello_list_from_db(rec)
        assert result == "Shipping completed"
    
    @pytest.mark.unit
    def test_determine_no_matching_list(self):
        """Test when no list matches the status."""
        rec = Mock()
        rec.fitup_comp = "O"
        rec.welded = ""
        rec.paint_comp = ""
        rec.ship = ""
        
        result = determine_trello_list_from_db(rec)
        assert result is None
    
    @pytest.mark.unit
    def test_determine_partial_status(self):
        """Test with partial status that doesn't match any list."""
        rec = Mock()
        rec.fitup_comp = "X"
        rec.welded = "X"
        rec.paint_comp = "O"
        rec.ship = ""
        
        result = determine_trello_list_from_db(rec)
        assert result is None


class TestIsFormulaCell:
    """Test formula cell detection."""
    
    @pytest.mark.unit
    def test_is_formula_with_formula_tf_true(self):
        """Test formula detection with formulaTF=True."""
        row = {
            "start_install_formula": "=SOME_FORMULA()",
            "start_install_formulaTF": True
        }
        
        result = is_formula_cell(row)
        assert result is True
    
    @pytest.mark.unit
    def test_is_formula_with_formula_string(self):
        """Test formula detection with formula string starting with =."""
        row = {
            "start_install_formula": "=SUM(A1:A10)",
            "start_install_formulaTF": False
        }
        
        result = is_formula_cell(row)
        assert result is True
    
    @pytest.mark.unit
    def test_is_not_formula_with_false_flag(self):
        """Test non-formula detection with formulaTF=False."""
        row = {
            "start_install_formula": "Not a formula",
            "start_install_formulaTF": False
        }
        
        result = is_formula_cell(row)
        assert result is False
    
    @pytest.mark.unit
    def test_is_not_formula_with_empty_formula(self):
        """Test non-formula detection with empty formula."""
        row = {
            "start_install_formula": "",
            "start_install_formulaTF": False
        }
        
        result = is_formula_cell(row)
        assert result is False
    
    @pytest.mark.unit
    def test_is_not_formula_with_none_formula(self):
        """Test non-formula detection with None formula."""
        row = {
            "start_install_formula": None,
            "start_install_formulaTF": False
        }
        
        result = is_formula_cell(row)
        assert result is False
    
    @pytest.mark.unit
    def test_is_formula_with_missing_fields(self):
        """Test formula detection with missing fields."""
        row = {}
        
        result = is_formula_cell(row)
        assert result is False
