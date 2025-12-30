# tests/test_dwl_service.py
"""
Simple tests to get started with pytest.
Run with: pytest tests/test_dwl_service.py -v
"""
import pytest
from app.brain.services.dwl_service import DraftingWorkLoadService, SubmittalOrderingService

# ==============================================================================
# STARTER TESTS - Read these first
# ==============================================================================

def test_validate_notes_with_none():
    """Test that None returns None."""
    result = DraftingWorkLoadService.validate_notes(None)
    assert result is None


def test_validate_notes_trims_whitespace():
    """Test that whitespace is trimmed."""
    result = DraftingWorkLoadService.validate_notes("  hello  ")
    assert result == "hello"


def test_validate_notes_empty_becomes_none():
    """Test that empty string becomes None."""
    result = DraftingWorkLoadService.validate_notes("   ")
    assert result is None

# ==============================================================================
# STATUS TESTS - Similar pattern
# ==============================================================================

def test_validate_status_accepts_valid():
    """Test that valid status is accepted."""
    is_valid, normalized, error = DraftingWorkLoadService.validate_drafting_status('STARTED')
    
    assert is_valid is True
    assert normalized == 'STARTED'
    assert error is None


def test_validate_status_rejects_invalid():
    """Test that invalid status is rejected."""
    is_valid, normalized, error = DraftingWorkLoadService.validate_drafting_status('INVALID')
    
    assert is_valid is False
    assert error is not None

# ==============================================================================
# ORDERING TESTS - Similar pattern
# ==============================================================================

def test_validate_order_number_accepts_valid():
    """Test that valid order number is accepted."""
    is_valid, error = SubmittalOrderingService.validate_order_number(1.0)
    assert is_valid is True
    assert error is None


def test_validate_order_number_rejects_invalid():
    """Test that invalid order number is rejected."""
    is_valid, error = SubmittalOrderingService.validate_order_number('INVALID')
    assert is_valid is False
    assert error is not None

def test_safe_float_conversion_integer():
    '''Test that order number is converted to float'''
    result = SubmittalOrderingService.safe_float_order(12)
    assert result == 12.0

def test_safe_float_conversion_none():
    '''Test that None returns None'''
    result = SubmittalOrderingService.safe_float_order(None)
    assert result is None

def test_safe_float_conversion_invalid():
    '''Test that invalid order number is rejected'''
    result = SubmittalOrderingService.safe_float_order('INVALID')
    assert result is None

def test_safe_float_conversion_string():
    '''Test that string is converted to float'''
    result = SubmittalOrderingService.safe_float_order('12')
    assert result == 12.0