"""
Tests for the Drafting Work Load service layer.
These tests verify service methods coordinate with the engine and handle database operations.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from app.brain.drafting_work_load.service import (
    DraftingWorkLoadService,
    SubmittalOrderingService,
    UrgencyService
)
from app.models import ProcoreSubmittal
from app import create_app


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
    fake_submittal.due_date = None
    fake_submittal.submittal_id = "submittal_123"
    return fake_submittal


# ==============================================================================
# DRAFTING WORK LOAD SERVICE TESTS
# ==============================================================================

class TestDraftingWorkLoadService:
    """Tests for DraftingWorkLoadService methods."""
    
    def test_update_notes_sets_the_value(self):
        """Test that update_notes sets the value."""
        submittal = create_fake_submittal()
        DraftingWorkLoadService.update_notes(submittal, 'Test New Note')
        assert submittal.notes == 'Test New Note'

    def test_update_notes_trims_whitespace(self):
        """Test that update_notes trims whitespace."""
        submittal = create_fake_submittal()
        DraftingWorkLoadService.update_notes(submittal, '  Test New Note  ')
        assert submittal.notes == 'Test New Note'

    def test_update_notes_sets_timestamp(self):
        """Test that last_updated is set when notes are updated."""
        submittal = create_fake_submittal()
        DraftingWorkLoadService.update_notes(submittal, "New notes")
        assert submittal.last_updated is not None
        assert isinstance(submittal.last_updated, datetime)

    def test_update_notes_clears_empty_notes(self):
        """Test that empty notes become None."""
        submittal = create_fake_submittal()
        submittal.notes = "Old notes"
        DraftingWorkLoadService.update_notes(submittal, "   ")
        assert submittal.notes is None

    def test_update_notes_with_none_clears_notes(self):
        """Test that passing None clears the notes."""
        submittal = create_fake_submittal()
        submittal.notes = "Old notes"
        DraftingWorkLoadService.update_notes(submittal, None)
        assert submittal.notes is None

    def test_update_drafting_status_with_valid_status(self):
        """Test updating with a valid status."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'STARTED')
        assert success is True
        assert error is None
        assert submittal.submittal_drafting_status == 'STARTED'

    def test_update_drafting_status_with_invalid_status(self):
        """Test that invalid status is rejected."""
        submittal = create_fake_submittal()
        submittal.submittal_drafting_status = 'HOLD'
        success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'INVALID')
        assert success is False
        assert error is not None
        assert "must be one of" in error
        assert submittal.submittal_drafting_status == 'HOLD'

    def test_update_drafting_status_sets_timestamp(self):
        """Test that timestamp is updated."""
        submittal = create_fake_submittal()
        DraftingWorkLoadService.update_drafting_status(submittal, 'STARTED')
        assert submittal.last_updated is not None
        assert isinstance(submittal.last_updated, datetime)

    def test_update_drafting_status_with_none_sets_empty(self):
        """Test that None is normalized to empty string."""
        submittal = create_fake_submittal()
        submittal.submittal_drafting_status = 'STARTED'
        success, error = DraftingWorkLoadService.update_drafting_status(submittal, None)
        assert success is True
        assert submittal.submittal_drafting_status == ''

    def test_update_drafting_status_with_each_valid_option(self):
        """Test all valid status options."""
        valid_statuses = ['', 'STARTED', 'NEED VIF', 'HOLD']
        
        for status in valid_statuses:
            submittal = create_fake_submittal()
            success, error = DraftingWorkLoadService.update_drafting_status(submittal, status)
            assert success is True, f"Status '{status}' should be valid"
            assert submittal.submittal_drafting_status == status

    def test_update_drafting_status_doesnt_update_timestamp_on_failure(self):
        """Test that timestamp isn't updated when validation fails."""
        submittal = create_fake_submittal()
        original_timestamp = datetime(2024, 1, 1)
        submittal.last_updated = original_timestamp
        success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'INVALID')
        assert success is False
        assert submittal.last_updated == original_timestamp

    def test_update_due_date_valid(self):
        """Test updating with a valid due date."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_due_date(submittal, '2024-01-15')
        assert success is True
        assert error is None
        assert submittal.due_date is not None
        assert submittal.due_date.year == 2024
        assert submittal.due_date.month == 1
        assert submittal.due_date.day == 15

    def test_update_due_date_none(self):
        """Test that None clears the due date."""
        submittal = create_fake_submittal()
        submittal.due_date = datetime(2024, 1, 15).date()
        success, error = DraftingWorkLoadService.update_due_date(submittal, None)
        assert success is True
        assert error is None
        assert submittal.due_date is None

    def test_update_due_date_invalid_format(self):
        """Test that invalid date format is rejected."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_due_date(submittal, '01/15/2024')
        assert success is False
        assert error is not None


# ==============================================================================
# SUBMITTAL ORDERING SERVICE TESTS
# ==============================================================================

class TestSubmittalOrderingService:
    """Tests for SubmittalOrderingService methods."""
    
    def test_safe_float_order_delegates_to_engine(self):
        """Test that safe_float_order delegates to engine."""
        result = SubmittalOrderingService.safe_float_order(12)
        assert result == 12.0

    def test_validate_order_number_delegates_to_engine(self):
        """Test that validate_order_number delegates to engine."""
        is_valid, error = SubmittalOrderingService.validate_order_number(1.0)
        assert is_valid is True
        assert error is None


# ==============================================================================
# URGENCY SERVICE TESTS
# ==============================================================================

class TestUrgencyService:
    """Tests for UrgencyService methods, particularly bump_order_number_to_urgent."""
    
    @pytest.fixture
    def app(self):
        """Create Flask application context for tests."""
        app = create_app()
        app.config['TESTING'] = True
        with app.app_context():
            yield app
    
    @pytest.fixture
    def mock_query(self, app):
        """Mock ProcoreSubmittal.query.filter().all() chain to avoid database hits."""
        mock_query_obj = Mock()
        patcher = patch('app.brain.drafting_work_load.service.ProcoreSubmittal.query', mock_query_obj)
        patcher.start()
        yield mock_query_obj
        patcher.stop()
    
    @pytest.fixture
    def sample_record(self):
        """Create a sample ProcoreSubmittal record."""
        record = Mock(spec=ProcoreSubmittal)
        record.order_number = 5  # Regular order number
        record.submittal_id = "submittal_123"
        return record
    
    def test_first_urgent_gets_09(self, mock_query, sample_record):
        """Test that the first urgent submittal gets 0.9."""
        mock_query.filter.return_value.all.return_value = []
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
    
    def test_second_urgent_shifts_first_up(self, mock_query, sample_record):
        """Test that when a second urgent arrives, the first shifts from 0.9 to 0.8."""
        existing_urgent = Mock(spec=ProcoreSubmittal)
        existing_urgent.order_number = 0.9
        existing_urgent.submittal_id = "submittal_456"
        
        mock_query.filter.return_value.all.return_value = [existing_urgent]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert existing_urgent.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_all_nine_slots_filled_bumps_regulars(self, mock_query, sample_record):
        """Test that when all 9 slots are filled, the regulars shift down by 1."""
        urgent_submittals = []
        for i in range(1, 10):
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        regular1 = Mock(spec=ProcoreSubmittal)
        regular1.order_number = 1.0
        regular1.submittal_id = "regular_1"
        
        regular2 = Mock(spec=ProcoreSubmittal)
        regular2.order_number = 2.0
        regular2.submittal_id = "regular_2"
        
        call_tracker = {'count': 0}
        
        def filter_side_effect(*args, **kwargs):
            mock_all = Mock()
            call_tracker['count'] += 1
            
            if call_tracker['count'] == 1:
                mock_all.all.return_value = urgent_submittals
            else:
                mock_all.all.return_value = [regular1, regular2]
            
            return mock_all
        
        mock_query.filter.side_effect = filter_side_effect
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 1
    
    def test_none_order_number_returns_false(self, mock_query, sample_record):
        """Test that None order number returns False."""
        sample_record.order_number = None
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number is None
    
    def test_already_decimal_returns_false(self, mock_query, sample_record):
        """Test that if order number is already a decimal (< 1), it returns False."""
        sample_record.order_number = 0.5
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number == 0.5
    
    def test_zero_order_number_returns_false(self, mock_query, sample_record):
        """Test that order number 0 returns False."""
        sample_record.order_number = 0
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number == 0
    
    def test_negative_order_number_returns_false(self, mock_query, sample_record):
        """Test that negative order number returns False."""
        sample_record.order_number = -1
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number == -1
    
    def test_multiple_urgent_with_room(self, mock_query, sample_record):
        """Test that multiple existing urgent submittals all shift up correctly."""
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.5
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.6
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=ProcoreSubmittal)
        urgent3.order_number = 0.7
        urgent3.submittal_id = "urgent_3"
        
        mock_query.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3
        ]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # Room for new so there should be no movement
        assert urgent1.order_number == pytest.approx(0.5, abs=0.001)  
        assert urgent2.order_number == pytest.approx(0.6, abs=0.001)  
        assert urgent3.order_number == pytest.approx(0.7, abs=0.001)
    
    def test_urgent_at_09_shifts_to_08(self, mock_query, sample_record):
        """Test that urgent at 0.9 shifts to 0.8 when new urgent arrives."""
        urgent = Mock(spec=ProcoreSubmittal)
        urgent.order_number = 0.9
        urgent.submittal_id = "urgent_1"
        
        mock_query.filter.return_value.all.return_value = [urgent]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert urgent.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_multiple_urgent_shifting_when_09_occupied(self, mock_query, sample_record):
        """Test that multiple urgent items all shift when 0.9 is occupied."""
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.7
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.8
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=ProcoreSubmittal)
        urgent3.order_number = 0.9
        urgent3.submittal_id = "urgent_3"
        
        mock_query.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3
        ]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert urgent1.order_number == pytest.approx(0.6, abs=0.001)
        assert urgent2.order_number == pytest.approx(0.7, abs=0.001)
        assert urgent3.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_all_nine_slots_filled_no_regular_orders(self, mock_query, sample_record):
        """Test that when all 9 slots are filled and no regular orders exist, new gets 1.0."""
        urgent_submittals = []
        for i in range(1, 10):
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        call_tracker = {'count': 0}
        
        def filter_side_effect(*args, **kwargs):
            mock_all = Mock()
            call_tracker['count'] += 1
            
            if call_tracker['count'] == 1:
                mock_all.all.return_value = urgent_submittals
            else:
                mock_all.all.return_value = []
            
            return mock_all
        
        mock_query.filter.side_effect = filter_side_effect
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 1.0
        for i, urgent in enumerate(urgent_submittals):
            assert urgent.order_number == pytest.approx((i + 1) * 0.1, abs=0.001)
    
    def test_all_nine_slots_filled_many_regular_orders(self, mock_query, sample_record):
        """Test that when all 9 slots are filled, all regular orders shift up correctly."""
        urgent_submittals = []
        for i in range(1, 10):
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        regulars = []
        for i in range(1, 6):
            regular = Mock(spec=ProcoreSubmittal)
            regular.order_number = float(i)
            regular.submittal_id = f"regular_{i}"
            regulars.append(regular)
        
        call_tracker = {'count': 0}
        
        def filter_side_effect(*args, **kwargs):
            mock_all = Mock()
            call_tracker['count'] += 1
            
            if call_tracker['count'] == 1:
                mock_all.all.return_value = urgent_submittals
            else:
                mock_all.all.return_value = regulars
            
            return mock_all
        
        mock_query.filter.side_effect = filter_side_effect
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 1.0
        for i, urgent in enumerate(urgent_submittals):
            assert urgent.order_number == pytest.approx((i + 1) * 0.1, abs=0.001)
        regular_dict = {r.submittal_id: r for r in regulars}
        assert regular_dict["regular_1"].order_number == 2.0
        assert regular_dict["regular_2"].order_number == 3.0
        assert regular_dict["regular_3"].order_number == 4.0
        assert regular_dict["regular_4"].order_number == 5.0
        assert regular_dict["regular_5"].order_number == 6.0
    
    def test_order_number_exactly_one(self, mock_query, sample_record):
        """Test that order number exactly 1.0 works correctly."""
        sample_record.order_number = 1.0
        
        mock_query.filter.return_value.all.return_value = []
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
    
    def test_three_urgent_items_one_shift(self, mock_query, sample_record):
        """Test that three urgent items (0.6, 0.7, 0.9) - only 0.9 shifts to 0.8 since 0.8 is open."""
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.6
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.7
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=ProcoreSubmittal)
        urgent3.order_number = 0.9
        urgent3.submittal_id = "urgent_3"
        
        mock_query.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3
        ]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert urgent1.order_number == pytest.approx(0.6, abs=0.001)
        assert urgent2.order_number == pytest.approx(0.7, abs=0.001)
        assert urgent3.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_current_submittal_excluded_from_query(self, mock_query, sample_record):
        """Test that current submittal is excluded from queries even if it has urgent order."""
        existing_urgent = Mock(spec=ProcoreSubmittal)
        existing_urgent.order_number = 0.9
        existing_urgent.submittal_id = "submittal_123"
        
        other_urgent = Mock(spec=ProcoreSubmittal)
        other_urgent.order_number = 0.9
        other_urgent.submittal_id = "urgent_other"
        
        mock_query.filter.return_value.all.return_value = [other_urgent]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert other_urgent.order_number == pytest.approx(0.8, abs=0.001)
        assert existing_urgent.order_number == 0.9
    
    def test_different_ball_in_court_ignored(self, mock_query, sample_record):
        """Test that urgent submittals with different ball_in_court are ignored."""
        other_urgent = Mock(spec=ProcoreSubmittal)
        other_urgent.order_number = 0.9
        other_urgent.submittal_id = "other_urgent"
        other_urgent.ball_in_court = "Drafter B"
        
        mock_query.filter.return_value.all.return_value = []
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert other_urgent.order_number == 0.9
    
    def test_ladder_progression_example(self, mock_query, sample_record):
        """Test a realistic ladder progression scenario - 0.9 not occupied, so no shifting."""
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.7
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.8
        urgent2.submittal_id = "urgent_2"
        
        mock_query.filter.return_value.all.return_value = [
            urgent1, urgent2
        ]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert urgent1.order_number == pytest.approx(0.7, abs=0.001)
        assert urgent2.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_eight_slots_filled_09_available(self, mock_query, sample_record):
        """Test that when 8 slots filled (0.1-0.8), new gets 0.9 without shifting."""
        urgent_submittals = []
        for i in range(1, 9):
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        mock_query.filter.return_value.all.return_value = urgent_submittals
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        for i, urgent in enumerate(urgent_submittals):
            assert urgent.order_number == pytest.approx((i + 1) * 0.1, abs=0.001)
    
    def test_single_order_compression(self, mock_query, sample_record):
        """Test that when a submittal pops from ball in court higher urgency submittals shift down."""
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.6
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.7
        urgent2.submittal_id = "urgent_2"

        urgent3 = Mock(spec=ProcoreSubmittal)
        urgent3.order_number = 0.8
        urgent3.submittal_id = "urgent_3"

        urgent4 = Mock(spec=ProcoreSubmittal)
        urgent4.order_number = 0.9
        urgent4.submittal_id = "urgent_4"
        
        mock_query.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3, urgent4
        ]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
