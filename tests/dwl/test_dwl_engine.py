"""
Tests for the Drafting Work Load engine layer (pure business logic).
These tests have no database or Flask dependencies - they test pure functions.
"""
import pytest
from app.brain.drafting_work_load.engine import (
    DraftingWorkLoadEngine,
    SubmittalOrderingEngine,
    UrgencyEngine,
    SubmittalOrderUpdate
)


# ==============================================================================
# DRAFTING WORK LOAD ENGINE TESTS
# ==============================================================================

class TestDraftingWorkLoadEngine:
    """Tests for DraftingWorkLoadEngine validation methods."""
    
    def test_validate_notes_with_none(self):
        """Test that None returns None."""
        result = DraftingWorkLoadEngine.validate_notes(None)
        assert result is None

    def test_validate_notes_trims_whitespace(self):
        """Test that whitespace is trimmed."""
        result = DraftingWorkLoadEngine.validate_notes("  hello  ")
        assert result == "hello"

    def test_validate_notes_empty_becomes_none(self):
        """Test that empty string becomes None."""
        result = DraftingWorkLoadEngine.validate_notes("   ")
        assert result is None

    def test_validate_drafting_status_accepts_valid(self):
        """Test that valid status is accepted."""
        is_valid, normalized, error = DraftingWorkLoadEngine.validate_drafting_status('STARTED')
        
        assert is_valid is True
        assert normalized == 'STARTED'
        assert error is None

    def test_validate_drafting_status_rejects_invalid(self):
        """Test that invalid status is rejected."""
        is_valid, normalized, error = DraftingWorkLoadEngine.validate_drafting_status('INVALID')
        
        assert is_valid is False
        assert error is not None

    def test_validate_drafting_status_none_becomes_empty(self):
        """Test that None is normalized to empty string."""
        is_valid, normalized, error = DraftingWorkLoadEngine.validate_drafting_status(None)
        
        assert is_valid is True
        assert normalized == ''
        assert error is None

    def test_validate_drafting_status_with_each_valid_option(self):
        """Test all valid status options."""
        valid_statuses = ['', 'STARTED', 'NEED VIF', 'HOLD']
        
        for status in valid_statuses:
            is_valid, normalized, error = DraftingWorkLoadEngine.validate_drafting_status(status)
            
            assert is_valid is True, f"Status '{status}' should be valid"
            assert normalized == status

    def test_validate_due_date_none(self):
        """Test that None due date is valid."""
        is_valid, normalized, error = DraftingWorkLoadEngine.validate_due_date(None)
        assert is_valid is True
        assert normalized is None
        assert error is None

    def test_validate_due_date_empty_string(self):
        """Test that empty string due date is valid."""
        is_valid, normalized, error = DraftingWorkLoadEngine.validate_due_date('')
        assert is_valid is True
        assert normalized is None
        assert error is None

    def test_validate_due_date_valid_format(self):
        """Test that valid ISO date format is accepted."""
        is_valid, normalized, error = DraftingWorkLoadEngine.validate_due_date('2024-01-15')
        assert is_valid is True
        assert normalized == '2024-01-15'
        assert error is None

    def test_validate_due_date_invalid_format(self):
        """Test that invalid date format is rejected."""
        is_valid, normalized, error = DraftingWorkLoadEngine.validate_due_date('01/15/2024')
        assert is_valid is False
        assert error is not None


# ==============================================================================
# SUBMITTAL ORDERING ENGINE TESTS
# ==============================================================================

class TestSubmittalOrderingEngine:
    """Tests for SubmittalOrderingEngine methods."""
    
    def test_safe_float_order_integer(self):
        """Test that order number is converted to float."""
        result = SubmittalOrderingEngine.safe_float_order(12)
        assert result == 12.0

    def test_safe_float_order_none(self):
        """Test that None returns None."""
        result = SubmittalOrderingEngine.safe_float_order(None)
        assert result is None

    def test_safe_float_order_invalid(self):
        """Test that invalid order number is rejected."""
        result = SubmittalOrderingEngine.safe_float_order('INVALID')
        assert result is None

    def test_safe_float_order_string(self):
        """Test that string is converted to float."""
        result = SubmittalOrderingEngine.safe_float_order('12')
        assert result == 12.0

    def test_validate_order_number_accepts_valid(self):
        """Test that valid order number is accepted."""
        is_valid, error = SubmittalOrderingEngine.validate_order_number(1.0)
        assert is_valid is True
        assert error is None

    def test_validate_order_number_rejects_invalid(self):
        """Test that invalid order number is rejected."""
        is_valid, error = SubmittalOrderingEngine.validate_order_number('INVALID')
        assert is_valid is False
        assert error is not None

    def test_validate_order_number_none_allowed(self):
        """Test that None is allowed."""
        is_valid, error = SubmittalOrderingEngine.validate_order_number(None)
        assert is_valid is True
        assert error is None

    def test_validate_order_number_zero_rejected(self):
        """Test that zero is rejected."""
        is_valid, error = SubmittalOrderingEngine.validate_order_number(0)
        assert is_valid is False
        assert error is not None

    def test_validate_order_number_urgency_slot_valid(self):
        """Test that valid urgency slots are accepted."""
        valid_slots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        for slot in valid_slots:
            is_valid, error = SubmittalOrderingEngine.validate_order_number(slot)
            assert is_valid is True, f"Slot {slot} should be valid"
            assert error is None

    def test_validate_order_number_urgency_slot_invalid(self):
        """Test that invalid urgency slots are rejected."""
        invalid_slots = [0.05, 0.15, 0.25, 0.95]
        for slot in invalid_slots:
            is_valid, error = SubmittalOrderingEngine.validate_order_number(slot)
            assert is_valid is False, f"Slot {slot} should be invalid"
            assert error is not None

    def test_categorize_submittals_separates_urgent_and_regular(self):
        """Test that submittals are correctly categorized."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 0.5},
            {'submittal_id': '2', 'order_number': 1.0},
            {'submittal_id': '3', 'order_number': 0.9},
            {'submittal_id': '4', 'order_number': 2.0},
            {'submittal_id': '5', 'order_number': None},
        ]
        
        urgent, regular = SubmittalOrderingEngine.categorize_submittals(submittals_data, 'exclude_id')
        
        assert len(urgent) == 2
        assert len(regular) == 2
        assert urgent[0]['submittal_id'] == '1'
        assert urgent[1]['submittal_id'] == '3'
        assert regular[0]['submittal_id'] == '2'
        assert regular[1]['submittal_id'] == '4'

    def test_categorize_submittals_excludes_specified_id(self):
        """Test that specified submittal ID is excluded."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 0.5},
            {'submittal_id': '2', 'order_number': 1.0},
        ]
        
        urgent, regular = SubmittalOrderingEngine.categorize_submittals(submittals_data, '1')
        
        assert len(urgent) == 0
        assert len(regular) == 1
        assert regular[0]['submittal_id'] == '2'

    def test_handle_set_to_null_regular_compression(self):
        """Test that setting to null does renumber regular submittals and compresses list."""
        submittal_data = {'submittal_id': '1', 'order_number': 1.0}
        all_group_submittals_data = [
            {'submittal_id': '1', 'order_number': 1.0},
            {'submittal_id': '2', 'order_number': 2.0},
            {'submittal_id': '3', 'order_number': 3.0},
        ]
        
        updates = SubmittalOrderingEngine.handle_set_to_null(submittal_data, all_group_submittals_data)
        
        # Should update submittal 1 to None, and compress list
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        assert update_dict['1'] is None
        assert update_dict['2'] == 1.0  # Compress
        assert update_dict['3'] == 2.0  # Compress

    def test_handle_set_to_null_urgency_compression(self):
        """Test that setting to null does renumber urgency submittals and compresses list."""
        submittal_data = {'submittal_id': '4', 'order_number': 0.8}
        all_group_submittals_data = [
            {'submittal_id': '1', 'order_number': 0.5},
            {'submittal_id': '2', 'order_number': 0.6},
            {'submittal_id': '3', 'order_number': 0.7},
            {'submittal_id': '4', 'order_number': 0.8},
            {'submittal_id': '5', 'order_number': 0.9},
        ]

        updates = SubmittalOrderingEngine.handle_set_to_null(submittal_data, all_group_submittals_data)
        
        # Should update submittal 4 to None, and compress list
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        assert update_dict['4'] is None
        assert update_dict['1'] == 0.6  # Compress
        assert update_dict['2'] == 0.7  # Compress
        assert update_dict['3'] == 0.8  # Compress
        assert update_dict['5'] == 0.9  # Compress
        

    def test_handle_set_to_urgent_compresses_slots(self):
        """Test that setting to urgent compresses urgency slots."""
        submittal_data = {'submittal_id': '1', 'order_number': 5.0}
        all_group_submittals_data = [
            {'submittal_id': '1', 'order_number': 5.0},
            {'submittal_id': '2', 'order_number': 0.7},
            {'submittal_id': '3', 'order_number': 0.9},
        ]
        
        updates = SubmittalOrderingEngine.handle_set_to_urgent(submittal_data, 0.9, all_group_submittals_data)
        
        # Should assign 0.9 to submittal 1, and compress existing urgent slots
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        assert '1' in update_dict
        # The compression logic should reassign slots

    def test_handle_set_to_regular_renumbers(self):
        """Test that setting to regular renumbers all regular positions."""
        submittal_data = {'submittal_id': '1', 'order_number': 0.5}
        all_group_submittals_data = [
            {'submittal_id': '1', 'order_number': 0.5},
            {'submittal_id': '2', 'order_number': 1.0},
            {'submittal_id': '3', 'order_number': 2.0},
        ]
        
        updates = SubmittalOrderingEngine.handle_set_to_regular(submittal_data, 2.0, all_group_submittals_data)
        
        # Should insert at position 2 and renumber
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        assert update_dict['1'] == 2.0
        assert update_dict['2'] == 1.0
        assert update_dict['3'] == 3.0

    def test_compress_orders_urgency_single_item(self):
        """Test compressing a single urgency item to 0.9."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 0.5},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        assert len(updates) == 1
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        assert update_dict['1'] == pytest.approx(0.9, abs=0.001)

    def test_compress_orders_urgency_multiple_items(self):
        """Test compressing multiple urgency items down to 0.9."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 0.2},  # Oldest
            {'submittal_id': '2', 'order_number': 0.5},
            {'submittal_id': '3', 'order_number': 0.8},  # Newest
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        assert len(updates) == 3
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        # Oldest (0.2) should get lowest slot (0.7), newest (0.8) should get 0.9
        assert update_dict['1'] == pytest.approx(0.7, abs=0.001)  # Oldest → lowest slot
        assert update_dict['2'] == pytest.approx(0.8, abs=0.001)
        assert update_dict['3'] == pytest.approx(0.9, abs=0.001)  # Newest → 0.9

    def test_compress_orders_urgency_all_nine_slots(self):
        """Test compressing all 9 urgency slots."""
        submittals_data = [
            {'submittal_id': str(i), 'order_number': i * 0.1}
            for i in range(1, 10)
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        # Items are already compressed correctly (0.1 through 0.9), so no updates needed
        assert len(updates) == 0

    def test_compress_orders_urgency_already_compressed(self):
        """Test that already compressed urgency items don't get updated."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 0.7},
            {'submittal_id': '2', 'order_number': 0.8},
            {'submittal_id': '3', 'order_number': 0.9},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        # Items are already compressed correctly (0.7, 0.8, 0.9 for 3 items), so no updates needed
        assert len(updates) == 0

    def test_compress_orders_regular_single_item(self):
        """Test compressing a single regular item to 1.0."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 5.0},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        assert len(updates) == 1
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        assert update_dict['1'] == 1.0

    def test_compress_orders_regular_multiple_items(self):
        """Test compressing multiple regular items down to 1.0."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 3.0},
            {'submittal_id': '2', 'order_number': 7.0},
            {'submittal_id': '3', 'order_number': 10.0},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        assert len(updates) == 3
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        # Should compress to 1, 2, 3 in order
        assert update_dict['1'] == 1.0
        assert update_dict['2'] == 2.0
        assert update_dict['3'] == 3.0

    def test_compress_orders_regular_already_compressed(self):
        """Test that already compressed regular items don't get updated."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 1.0},
            {'submittal_id': '2', 'order_number': 2.0},
            {'submittal_id': '3', 'order_number': 3.0},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        # Should not update since they're already compressed correctly
        assert len(updates) == 0

    def test_compress_orders_mixed_urgency_and_regular(self):
        """Test compressing both urgency and regular items together."""
        submittals_data = [
            {'submittal_id': 'urgent_1', 'order_number': 0.3},
            {'submittal_id': 'urgent_2', 'order_number': 0.6},
            {'submittal_id': 'regular_1', 'order_number': 5.0},
            {'submittal_id': 'regular_2', 'order_number': 8.0},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        assert len(updates) == 4
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        # Urgency should compress to 0.8, 0.9
        assert update_dict['urgent_1'] == pytest.approx(0.8, abs=0.001)
        assert update_dict['urgent_2'] == pytest.approx(0.9, abs=0.001)
        # Regular should compress to 1, 2
        assert update_dict['regular_1'] == 1.0
        assert update_dict['regular_2'] == 2.0

    def test_compress_orders_with_null_values(self):
        """Test that NULL order values are ignored."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': 0.5},
            {'submittal_id': '2', 'order_number': None},
            {'submittal_id': '3', 'order_number': 3.0},
            {'submittal_id': '4', 'order_number': None},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        
        # Should only update items with order numbers
        assert len(updates) == 2
        update_dict = {submittal_id: new_order for submittal_id, new_order in updates}
        assert '1' in update_dict
        assert '3' in update_dict
        assert '2' not in update_dict
        assert '4' not in update_dict

    def test_compress_orders_empty_list(self):
        """Test compressing an empty list."""
        updates = SubmittalOrderingEngine.compress_orders([])
        assert len(updates) == 0

    def test_compress_orders_only_null_values(self):
        """Test compressing a list with only NULL values."""
        submittals_data = [
            {'submittal_id': '1', 'order_number': None},
            {'submittal_id': '2', 'order_number': None},
        ]
        
        updates = SubmittalOrderingEngine.compress_orders(submittals_data)
        assert len(updates) == 0


# ==============================================================================
# URGENCY ENGINE TESTS
# ==============================================================================

class TestUrgencyEngine:
    """Tests for UrgencyEngine methods."""
    
    def test_check_submitter_pending_in_workflow_no_approvers(self):
        """Test with no approvers."""
        result = UrgencyEngine.check_submitter_pending_in_workflow([])
        assert result is False

    def test_check_submitter_pending_in_workflow_submitter_not_pending(self):
        """Test when submitter is not pending in next workflow group."""
        approvers = [
            {
                'workflow_group_number': 0,
                'user': {'name': 'John Doe', 'login': 'john.doe'}
            },
            {
                'workflow_group_number': 1,
                'user': {'name': 'Jane Smith', 'login': 'jane.smith'},
                'response': {'name': 'Approved'}
            }
        ]
        result = UrgencyEngine.check_submitter_pending_in_workflow(approvers)
        assert result is False

    def test_check_submitter_pending_in_workflow_submitter_is_pending(self):
        """Test when submitter is pending in next workflow group."""
        approvers = [
            {
                'workflow_group_number': 0,
                'user': {'name': 'John Doe', 'login': 'john.doe'}
            },
            {
                'workflow_group_number': 1,
                'user': {'name': 'John Doe', 'login': 'john.doe'},
                'response': {'name': 'Pending'}
            }
        ]
        result = UrgencyEngine.check_submitter_pending_in_workflow(approvers)
        assert result is True

    def test_calculate_bump_updates_first_urgent_gets_09(self):
        """Test that first urgent submittal gets 0.9."""
        can_bump, new_order, urgent_updates, regular_updates = UrgencyEngine.calculate_bump_updates(
            current_order=5.0,
            existing_urgent_submittals_data=[],
            existing_regular_submittals_data=[]
        )
        
        assert can_bump is True
        assert new_order == 0.9
        assert len(urgent_updates) == 0
        assert len(regular_updates) == 0

    def test_calculate_bump_updates_second_urgent_shifts_first(self):
        """Test that second urgent shifts first from 0.9 to 0.8."""
        existing_urgent = [{'submittal_id': 'urgent_1', 'order_number': 0.9}]
        
        can_bump, new_order, urgent_updates, regular_updates = UrgencyEngine.calculate_bump_updates(
            current_order=5.0,
            existing_urgent_submittals_data=existing_urgent,
            existing_regular_submittals_data=[]
        )
        
        assert can_bump is True
        assert new_order == 0.9
        assert len(urgent_updates) == 1
        assert urgent_updates[0][0] == 'urgent_1'
        assert urgent_updates[0][1] == pytest.approx(0.8, abs=0.001)

    def test_calculate_bump_updates_all_slots_filled_bumps_to_regular(self):
        """Test that when all 9 slots are filled, new gets order 1."""
        existing_urgent = [
            {'submittal_id': f'urgent_{i}', 'order_number': i * 0.1}
            for i in range(1, 10)
        ]
        existing_regular = [
            {'submittal_id': 'regular_1', 'order_number': 1.0},
            {'submittal_id': 'regular_2', 'order_number': 2.0},
        ]
        
        can_bump, new_order, urgent_updates, regular_updates = UrgencyEngine.calculate_bump_updates(
            current_order=5.0,
            existing_urgent_submittals_data=existing_urgent,
            existing_regular_submittals_data=existing_regular
        )
        
        assert can_bump is True
        assert new_order == 1.0
        assert len(regular_updates) == 2
        # Regular orders should shift up by 1
        regular_dict = {submittal_id: new_order for submittal_id, new_order in regular_updates}
        assert regular_dict['regular_1'] == 2.0
        assert regular_dict['regular_2'] == 3.0

    def test_calculate_bump_updates_invalid_order_returns_false(self):
        """Test that invalid order number returns False."""
        can_bump, new_order, urgent_updates, regular_updates = UrgencyEngine.calculate_bump_updates(
            current_order=0.5,  # Already urgent
            existing_urgent_submittals_data=[],
            existing_regular_submittals_data=[]
        )
        
        assert can_bump is False
        assert new_order is None
        assert len(urgent_updates) == 0
        assert len(regular_updates) == 0

