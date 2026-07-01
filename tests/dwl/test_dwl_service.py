"""
Tests for the Drafting Work Load service layer.
These tests verify service methods coordinate with the engine and handle database operations.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from app.brain.drafting_work_load.service import (
    DraftingWorkLoadService,
    SubmittalOrderingService,
    UrgencyService,
    SubmittalOrderUpdate,
)
from app.models import Submittals
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
    
    # NOTE: input validation/normalization (trimming, empty→None, None→'',
    # date-format parsing, the full valid-status set) is covered by the engine
    # tests in test_dwl_engine.py. These service tests only pin the behavior the
    # service layer adds on top: writing the value onto the submittal, stamping
    # last_updated on success, and leaving both untouched on failure.

    def test_update_notes_writes_value_and_stamps(self):
        """Service writes the validated note onto the submittal and stamps it."""
        submittal = create_fake_submittal()
        DraftingWorkLoadService.update_notes(submittal, "New notes")
        assert submittal.notes == "New notes"
        assert isinstance(submittal.last_updated, datetime)

    def test_update_drafting_status_writes_value_and_stamps(self):
        """Service writes a valid status onto the submittal and stamps it."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'STARTED')
        assert success is True
        assert error is None
        assert submittal.submittal_drafting_status == 'STARTED'
        assert isinstance(submittal.last_updated, datetime)

    def test_update_drafting_status_failure_leaves_value_and_stamp_untouched(self):
        """On a rejected status the submittal value and timestamp are unchanged."""
        submittal = create_fake_submittal()
        submittal.submittal_drafting_status = 'HOLD'
        original_timestamp = datetime(2024, 1, 1)
        submittal.last_updated = original_timestamp
        success, error = DraftingWorkLoadService.update_drafting_status(submittal, 'INVALID')
        assert success is False
        assert error is not None
        assert submittal.submittal_drafting_status == 'HOLD'
        assert submittal.last_updated == original_timestamp

    def test_update_due_date_writes_parsed_date(self):
        """Service writes the parsed date onto the submittal."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_due_date(submittal, '2024-01-15')
        assert success is True
        assert error is None
        assert (submittal.due_date.year, submittal.due_date.month, submittal.due_date.day) == (2024, 1, 15)

    def test_update_due_date_invalid_format_rejected(self):
        """Invalid date format is rejected at the service boundary."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_due_date(submittal, '01/15/2024')
        assert success is False
        assert error is not None

    def test_update_due_date_with_gc_schedule_backdates_60_business_days(self):
        """A GC jobsite schedule date persists itself and backdates due_date 60
        business days from it (12 weeks, so a Monday anchor lands on a Monday)."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_due_date(
            submittal, gc_jobsite_schedule_date='2026-11-30'
        )
        assert success is True
        assert error is None
        assert submittal.gc_jobsite_schedule_date == date(2026, 11, 30)
        assert submittal.due_date == date(2026, 9, 7)
        assert isinstance(submittal.last_updated, datetime)

    def test_update_due_date_manual_leaves_gc_schedule_date_untouched(self):
        """Setting due_date directly doesn't clear a previously-stored GC schedule
        date -- it's tracked independently for long-term reporting."""
        submittal = create_fake_submittal()
        submittal.gc_jobsite_schedule_date = date(2026, 11, 30)
        success, error = DraftingWorkLoadService.update_due_date(submittal, '2024-01-15')
        assert success is True
        assert error is None
        assert submittal.gc_jobsite_schedule_date == date(2026, 11, 30)
        assert (submittal.due_date.year, submittal.due_date.month, submittal.due_date.day) == (2024, 1, 15)

    def test_update_due_date_invalid_gc_schedule_date_rejected(self):
        """Invalid GC schedule date format is rejected without touching either field."""
        submittal = create_fake_submittal()
        success, error = DraftingWorkLoadService.update_due_date(
            submittal, gc_jobsite_schedule_date='11/30/2026'
        )
        assert success is False
        assert error is not None
        assert submittal.due_date is None

    @patch('app.brain.drafting_work_load.service.Submittals')
    def test_get_dwl_submittals_open_tab(self, mock_submittals):
        """Test that get_dwl_submittals(tab='open') filters by status=='Open'."""
        mock_query_result = Mock()
        mock_query_result.all.return_value = []
        mock_submittals.query.filter.return_value = mock_query_result

        result = DraftingWorkLoadService.get_dwl_submittals(None, tab='open')

        assert result == []
        mock_submittals.query.filter.assert_called_once()

    @patch('app.brain.drafting_work_load.service.Submittals')
    def test_get_dwl_submittals_with_job_numbers_filter(self, mock_submittals):
        """Test that job_numbers_filter applies a second filter on project_number."""
        mock_base = Mock()
        mock_final = Mock()
        fake_submittal = Mock()
        mock_final.all.return_value = [fake_submittal]
        mock_base.filter.return_value = mock_final
        mock_submittals.query.filter.return_value = mock_base

        result = DraftingWorkLoadService.get_dwl_submittals(['J001', 'J002'], tab='open')

        assert len(result) == 1
        # Verify the second filter (job_numbers) was applied
        mock_base.filter.assert_called_once()


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

    def test_step_order_delegates_to_engine(self):
        """Test that step_order calls the engine and returns (model, order) pairs."""
        s1 = Mock()
        s1.submittal_id = 'A'
        s1.order_number = 1.0
        s2 = Mock()
        s2.submittal_id = 'B'
        s2.order_number = 2.0

        results = SubmittalOrderingService.step_order(s2, 'up', [s1, s2])

        assert len(results) == 2
        result_map = {subm.submittal_id: order for subm, order in results}
        assert result_map['B'] == 1.0
        assert result_map['A'] == 2.0

    def test_resort_ordered_submittals_returns_model_pairs(self):
        """Test that resort_ordered_submittals compresses and returns (model, order) pairs."""
        s1 = Mock()
        s1.submittal_id = 'A'
        s1.order_number = 4.0
        s2 = Mock()
        s2.submittal_id = 'B'
        s2.order_number = 7.0

        results = SubmittalOrderingService.resort_ordered_submittals([s1, s2])

        assert len(results) == 2
        result_map = {subm.submittal_id: order for subm, order in results}
        assert result_map['A'] == 1.0
        assert result_map['B'] == 2.0

    def test_calculate_updates_wraps_engine(self):
        """Test that calculate_updates converts models→dicts→engine→models."""
        s1 = Mock()
        s1.submittal_id = 'A'
        s1.order_number = 1.0

        update_request = SubmittalOrderUpdate(
            submittal_id='A', new_order=None, old_order=1.0, ball_in_court='Drafter A'
        )
        results = SubmittalOrderingService.calculate_updates(update_request, [s1])

        assert len(results) == 1
        subm, new_order = results[0]
        assert subm.submittal_id == 'A'
        assert new_order is None


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
        """Mock Submittals.query.filter().all() chain to avoid database hits."""
        mock_query_obj = Mock()
        patcher = patch('app.brain.drafting_work_load.service.Submittals.query', mock_query_obj)
        patcher.start()
        yield mock_query_obj
        patcher.stop()
    
    @pytest.fixture
    def sample_record(self):
        """Create a sample Submittals record."""
        record = Mock(spec=Submittals)
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
        existing_urgent = Mock(spec=Submittals)
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
            urgent = Mock(spec=Submittals)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        regular1 = Mock(spec=Submittals)
        regular1.order_number = 1.0
        regular1.submittal_id = "regular_1"
        
        regular2 = Mock(spec=Submittals)
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
        urgent1 = Mock(spec=Submittals)
        urgent1.order_number = 0.5
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=Submittals)
        urgent2.order_number = 0.6
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=Submittals)
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
        urgent = Mock(spec=Submittals)
        urgent.order_number = 0.9
        urgent.submittal_id = "urgent_1"
        
        mock_query.filter.return_value.all.return_value = [urgent]
        
        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        assert urgent.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_multiple_urgent_shifting_when_09_occupied(self, mock_query, sample_record):
        """Test that multiple urgent items all shift when 0.9 is occupied."""
        urgent1 = Mock(spec=Submittals)
        urgent1.order_number = 0.7
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=Submittals)
        urgent2.order_number = 0.8
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=Submittals)
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
            urgent = Mock(spec=Submittals)
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
            urgent = Mock(spec=Submittals)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        regulars = []
        for i in range(1, 6):
            regular = Mock(spec=Submittals)
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
        urgent1 = Mock(spec=Submittals)
        urgent1.order_number = 0.6
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=Submittals)
        urgent2.order_number = 0.7
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=Submittals)
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
        existing_urgent = Mock(spec=Submittals)
        existing_urgent.order_number = 0.9
        existing_urgent.submittal_id = "submittal_123"
        
        other_urgent = Mock(spec=Submittals)
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
        other_urgent = Mock(spec=Submittals)
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
        urgent1 = Mock(spec=Submittals)
        urgent1.order_number = 0.7
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=Submittals)
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
            urgent = Mock(spec=Submittals)
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
        urgent1 = Mock(spec=Submittals)
        urgent1.order_number = 0.6
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=Submittals)
        urgent2.order_number = 0.7
        urgent2.submittal_id = "urgent_2"

        urgent3 = Mock(spec=Submittals)
        urgent3.order_number = 0.8
        urgent3.submittal_id = "urgent_3"

        urgent4 = Mock(spec=Submittals)
        urgent4.order_number = 0.9
        urgent4.submittal_id = "urgent_4"
        
        mock_query.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3, urgent4
        ]

        result = UrgencyService.bump_order_number_to_urgent(sample_record, "submittal_123", "Drafter A")

        assert result is True
        assert sample_record.order_number == 0.9

    def test_bump_unordered_to_ordered_appends_to_end(self, mock_query, sample_record):
        """Test that a null order_number submittal gets 1.0 when no existing ordered submittals."""
        sample_record.order_number = None
        mock_query.filter.return_value.all.return_value = []

        result = UrgencyService.bump_unordered_to_ordered(sample_record, "submittal_123", "Drafter A")

        assert result is True
        assert sample_record.order_number == 1.0
