# tests/test_dwl_service.py
"""
Simple tests to get started with pytest.
Run with: pytest tests/test_dwl_service.py -v
"""
import pytest
from unittest.mock import Mock
from app.brain.drafting_work_load.service import DraftingWorkLoadService, SubmittalOrderingService
from datetime import datetime

# ==============================================================================
# HELPER: Create a fake submittal for testing
# ==============================================================================

def create_fake_submittal():
    """
    Create a fake submittal object for testing.
    We use Mock() to create a fake object that acts like a real submittal
    but doesn't need a database.
    """
    fake_submittal = Mock()
    fake_submittal.notes = None
    fake_submittal.submittal_drafting_status = ''
    fake_submittal.last_updated = None
    return fake_submittal

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

# ==============================================================================
# Update Notes Tests
# ==============================================================================
def test_update_notes_sets_the_value():
    # Assert
    submittal = create_fake_submittal()
    # Act
    DraftingWorkLoadService.update_notes(submittal, 'Test New Note')
    # Assert
    assert submittal.notes == 'Test New Note'

def test_update_notes_trims_whitespace():
    submittal = create_fake_submittal()
    DraftingWorkLoadService.update_notes(submittal, '  Test New Note  ')
    assert submittal.notes == 'Test New Note'

def test_update_notes_sets_timestamp():
    """Test that last_updated is set when notes are updated."""
    # ARRANGE
    submittal = create_fake_submittal()
    
    # ACT
    DraftingWorkLoadService.update_notes(submittal, "New notes")
    
    # ASSERT - Timestamp should be set
    assert submittal.last_updated is not None
    assert isinstance(submittal.last_updated, datetime)

def test_update_notes_clears_empty_notes():
    """Test that empty notes become None."""
    # ARRANGE
    submittal = create_fake_submittal()
    submittal.notes = "Old notes"  # Start with existing notes
    
    # ACT - Set to empty string
    DraftingWorkLoadService.update_notes(submittal, "   ")
    
    # ASSERT - Should be None, not empty string
    assert submittal.notes is None


def test_update_notes_with_none_clears_notes():
    """Test that passing None clears the notes."""
    # ARRANGE
    submittal = create_fake_submittal()
    submittal.notes = "Old notes"
    
    # ACT
    DraftingWorkLoadService.update_notes(submittal, None)
    
    # ASSERT
    assert submittal.notes is None

#==============================================================================
# UPDATE DRAFTING STATUS TESTS
# ==============================================================================

def test_update_status_with_valid_status():
    """Test updating with a valid status."""
    # ARRANGE
    submittal = create_fake_submittal()
    
    # ACT
    success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'STARTED')
    
    # ASSERT - Should succeed
    assert success is True
    assert error is None
    # Check the status was actually set
    assert submittal.submittal_drafting_status == 'STARTED'


def test_update_status_with_invalid_status():
    """Test that invalid status is rejected."""
    # ARRANGE
    submittal = create_fake_submittal()
    submittal.submittal_drafting_status = 'HOLD'  # Start with valid status
    
    # ACT
    success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'INVALID')
    
    # ASSERT - Should fail
    assert success is False
    assert error is not None
    assert "must be one of" in error
    # Original status should be unchanged
    assert submittal.submittal_drafting_status == 'HOLD'


def test_update_status_sets_timestamp():
    """Test that timestamp is updated."""
    # ARRANGE
    submittal = create_fake_submittal()
    
    # ACT
    DraftingWorkLoadService.update_drafting_status(submittal, 'STARTED')
    
    # ASSERT
    assert submittal.last_updated is not None
    assert isinstance(submittal.last_updated, datetime)


def test_update_status_with_none_sets_empty():
    """Test that None is normalized to empty string."""
    # ARRANGE
    submittal = create_fake_submittal()
    submittal.submittal_drafting_status = 'STARTED'
    
    # ACT
    success, error = DraftingWorkLoadService.update_drafting_status(submittal, None)
    
    # ASSERT
    assert success is True
    assert submittal.submittal_drafting_status == ''


def test_update_status_with_each_valid_option():
    """Test all valid status options."""
    valid_statuses = ['', 'STARTED', 'NEED VIF', 'HOLD']
    
    for status in valid_statuses:
        # ARRANGE
        submittal = create_fake_submittal()
        
        # ACT
        success, error = DraftingWorkLoadService.update_drafting_status(submittal, status)
        
        # ASSERT
        assert success is True, f"Status '{status}' should be valid"
        assert submittal.submittal_drafting_status == status


def test_update_status_doesnt_update_timestamp_on_failure():
    """Test that timestamp isn't updated when validation fails."""
    # ARRANGE
    submittal = create_fake_submittal()
    original_timestamp = datetime(2024, 1, 1)  # Set a specific timestamp
    submittal.last_updated = original_timestamp
    
    # ACT
    success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'INVALID')
    
    # ASSERT - Timestamp should be unchanged
    assert success is False
    assert submittal.last_updated == original_timestamp