"""
Tests for the ladder urgency system in _bump_order_number_to_decimal.

The ladder system works as follows:
- 0.1 = MOST urgent (oldest, been waiting longest)
- 0.9 = LEAST urgent (newest, just arrived)
- New urgent submittal gets 0.9 (least urgent position)
- All existing urgent submittals shift UP by 0.1 (toward 0.1)
- If all 9 slots are filled, the one at 0.1 gets bumped to order 1 (regular status)
- When bumping to regular, all regular orders (>= 1) shift DOWN by 1
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.procore.procore import _bump_order_number_to_decimal
from app.models import ProcoreSubmittal


class TestLadderUrgencySystem:
    """Test suite for the ladder urgency bump system."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        with patch('app.procore.procore.db.session') as mock_session:
            yield mock_session
    
    @pytest.fixture
    def sample_record(self):
        """Create a sample ProcoreSubmittal record."""
        record = Mock(spec=ProcoreSubmittal)
        record.order_number = 5  # Regular order number
        record.submittal_id = "submittal_123"
        return record
    
    def test_first_urgent_gets_09(self, mock_db_session, sample_record):
        """Test that the first urgent submittal gets 0.9."""
        # No existing urgent submittals
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
    
    def test_second_urgent_shifts_first_up(self, mock_db_session, sample_record):
        """Test that when a second urgent arrives, the first shifts from 0.9 to 0.8."""
        # Create existing urgent submittal at 0.9
        existing_urgent = Mock(spec=ProcoreSubmittal)
        existing_urgent.order_number = 0.9
        existing_urgent.submittal_id = "submittal_456"
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [existing_urgent]
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # 0.9 - 0.1 = 0.8 (shifts down toward 0.1 = most urgent)
        assert existing_urgent.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_multiple_urgent_with_room(self, mock_db_session, sample_record):
        """Test that multiple existing urgent submittals all shift up correctly."""
        # Create 3 existing urgent submittals that won't exceed 0.9 when shifted
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.5
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.6
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=ProcoreSubmittal)
        urgent3.order_number = 0.7
        urgent3.submittal_id = "urgent_3"
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3
        ]
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # Room for new so there should be no movement
        assert urgent1.order_number == pytest.approx(0.5, abs=0.001)  
        assert urgent2.order_number == pytest.approx(0.6, abs=0.001)  
        assert urgent3.order_number == pytest.approx(0.7, abs=0.001)  
    
    def test_urgent_at_09_shifts_to_08(self, mock_db_session, sample_record):
        """Test that urgent at 0.9 shifts to 0.8 when new urgent arrives."""
        urgent = Mock(spec=ProcoreSubmittal)
        urgent.order_number = 0.9
        urgent.submittal_id = "urgent_1"
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [urgent]
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # 0.9 - 0.1 = 0.8 (shifts down toward 0.1 = most urgent)
        assert urgent.order_number == pytest.approx(0.8, abs=0.001)
    
    def test_all_nine_slots_filled_bumps_regulars(self, mock_db_session, sample_record):
        """Test that when all 9 slots are filled, the regulars shift down by 1 to make room for the new urgent at 1."""
        # Create 9 urgent submittals filling all slots
        urgent_submittals = []
        for i in range(1, 10):  # 0.1 through 0.9
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        # Create regular submittals
        regular1 = Mock(spec=ProcoreSubmittal)
        regular1.order_number = 1.0
        regular1.submittal_id = "regular_1"
        
        regular2 = Mock(spec=ProcoreSubmittal)
        regular2.order_number = 2.0
        regular2.submittal_id = "regular_2"
        
        # Set up query side effects - first call returns urgent, second returns regular
        call_tracker = {'count': 0}
        
        def query_side_effect(model):
            if model == ProcoreSubmittal:
                mock_filter = Mock()
                call_tracker['count'] += 1
                
                if call_tracker['count'] == 1:
                    # First call: urgent submittals
                    mock_filter.filter.return_value.all.return_value = urgent_submittals
                else:
                    # Second call: regular submittals
                    mock_filter.filter.return_value.all.return_value = [regular1, regular2]
                
                return mock_filter
            return Mock()
        
        mock_db_session.query.side_effect = query_side_effect
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 1
        
        # The one at 1 should be bumped down to 2
        oldest_urgent = urgent_submittals[0]  # The one at 0.1
        assert oldest_urgent.order_number == 0.1
        
        # All other urgent should be unaffected (use pytest.approx for floating point precision)
        assert urgent_submittals[1].order_number == pytest.approx(0.2, abs=0.001)
        assert urgent_submittals[2].order_number == pytest.approx(0.3, abs=0.001)
        assert urgent_submittals[3].order_number == pytest.approx(0.4, abs=0.001)
        assert urgent_submittals[4].order_number == pytest.approx(0.5, abs=0.001)
        assert urgent_submittals[5].order_number == pytest.approx(0.6, abs=0.001)
        assert urgent_submittals[6].order_number == pytest.approx(0.7, abs=0.001)
        assert urgent_submittals[7].order_number == pytest.approx(0.8, abs=0.001)
    
    def test_multiple_urgent_shifting_when_09_occupied(self, mock_db_session, sample_record):
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
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3
        ]
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # All should shift down by 0.1 since 0.9 is occupied
        assert urgent1.order_number == pytest.approx(0.6, abs=0.001)  # 0.7 -> 0.6
        assert urgent2.order_number == pytest.approx(0.7, abs=0.001)  # 0.8 -> 0.7
        assert urgent3.order_number == pytest.approx(0.8, abs=0.001)  # 0.9 -> 0.8
    
    def test_all_nine_slots_filled_no_regular_orders(self, mock_db_session, sample_record):
        """Test that when all 9 slots are filled and no regular orders exist, new gets 1.0."""
        urgent_submittals = []
        for i in range(1, 10):  # 0.1 through 0.9
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        call_tracker = {'count': 0}
        
        def query_side_effect(model):
            if model == ProcoreSubmittal:
                mock_filter = Mock()
                call_tracker['count'] += 1
                
                if call_tracker['count'] == 1:
                    # First call: urgent submittals
                    mock_filter.filter.return_value.all.return_value = urgent_submittals
                else:
                    # Second call: regular submittals (empty)
                    mock_filter.filter.return_value.all.return_value = []
                
                return mock_filter
            return Mock()
        
        mock_db_session.query.side_effect = query_side_effect
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 1.0
        # All urgent should remain unchanged
        for i, urgent in enumerate(urgent_submittals):
            assert urgent.order_number == pytest.approx((i + 1) * 0.1, abs=0.001)
    
    def test_all_nine_slots_filled_many_regular_orders(self, mock_db_session, sample_record):
        """Test that when all 9 slots are filled, all regular orders shift up correctly."""
        urgent_submittals = []
        for i in range(1, 10):  # 0.1 through 0.9
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        # Create 5 regular submittals
        regulars = []
        for i in range(1, 6):
            regular = Mock(spec=ProcoreSubmittal)
            regular.order_number = float(i)
            regular.submittal_id = f"regular_{i}"
            regulars.append(regular)
        
        call_tracker = {'count': 0}
        
        def query_side_effect(model):
            if model == ProcoreSubmittal:
                mock_filter = Mock()
                call_tracker['count'] += 1
                
                if call_tracker['count'] == 1:
                    # First call: urgent submittals
                    mock_filter.filter.return_value.all.return_value = urgent_submittals
                else:
                    # Second call: regular submittals
                    mock_filter.filter.return_value.all.return_value = regulars
                
                return mock_filter
            return Mock()
        
        mock_db_session.query.side_effect = query_side_effect
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 1.0
        # All urgent should remain unchanged
        for i, urgent in enumerate(urgent_submittals):
            assert urgent.order_number == pytest.approx((i + 1) * 0.1, abs=0.001)
        # All regular should shift up by 1 (they're processed in reverse order, so check by submittal_id)
        regular_dict = {r.submittal_id: r for r in regulars}
        assert regular_dict["regular_1"].order_number == 2.0  # 1 -> 2
        assert regular_dict["regular_2"].order_number == 3.0  # 2 -> 3
        assert regular_dict["regular_3"].order_number == 4.0  # 3 -> 4
        assert regular_dict["regular_4"].order_number == 5.0  # 4 -> 5
        assert regular_dict["regular_5"].order_number == 6.0  # 5 -> 6
    
    def test_non_integer_order_number(self, mock_db_session, sample_record):
        """Test that non-integer order numbers >= 1 still work (e.g., 5.0, 10.0)."""
        sample_record.order_number = 5.0  # Float but effectively integer
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
    
    def test_order_number_exactly_one(self, mock_db_session, sample_record):
        """Test that order number exactly 1.0 works correctly."""
        sample_record.order_number = 1.0
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
    
    def test_three_urgent_items_shifting(self, mock_db_session, sample_record):
        """Test that three urgent items (0.6, 0.7, 0.9) all shift when 0.9 is occupied."""
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.6
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.7
        urgent2.submittal_id = "urgent_2"
        
        urgent3 = Mock(spec=ProcoreSubmittal)
        urgent3.order_number = 0.9
        urgent3.submittal_id = "urgent_3"
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            urgent1, urgent2, urgent3
        ]
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # All should shift down by 0.1 since 0.9 is occupied
        assert urgent1.order_number == pytest.approx(0.5, abs=0.001)  # 0.6 -> 0.5
        assert urgent2.order_number == pytest.approx(0.6, abs=0.001)  # 0.7 -> 0.6
        assert urgent3.order_number == pytest.approx(0.8, abs=0.001)  # 0.9 -> 0.8
    
    def test_current_submittal_excluded_from_query(self, mock_db_session, sample_record):
        """Test that current submittal is excluded from queries even if it has urgent order."""
        # Create an urgent submittal with same ID as current (should be excluded)
        existing_urgent = Mock(spec=ProcoreSubmittal)
        existing_urgent.order_number = 0.9
        existing_urgent.submittal_id = "submittal_123"  # Same as sample_record
        
        # Also create another urgent with different ID at 0.9 (so 0.9 is occupied)
        other_urgent = Mock(spec=ProcoreSubmittal)
        other_urgent.order_number = 0.9
        other_urgent.submittal_id = "urgent_other"
        
        # Query should exclude current submittal, so only return other_urgent
        mock_db_session.query.return_value.filter.return_value.all.return_value = [other_urgent]
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # other_urgent should shift since 0.9 is occupied
        assert other_urgent.order_number == pytest.approx(0.8, abs=0.001)  # 0.9 -> 0.8
        # existing_urgent (with same ID as current) should not be affected since it's excluded from query
        assert existing_urgent.order_number == 0.9
    
    def test_none_order_number_returns_false(self, mock_db_session, sample_record):
        """Test that None order number returns False."""
        sample_record.order_number = None
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number is None
    
    def test_already_decimal_returns_false(self, mock_db_session, sample_record):
        """Test that if order number is already a decimal (< 1), it returns False."""
        sample_record.order_number = 0.5
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number == 0.5
    
    def test_zero_order_number_returns_false(self, mock_db_session, sample_record):
        """Test that order number 0 returns False."""
        sample_record.order_number = 0
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number == 0
    
    def test_negative_order_number_returns_false(self, mock_db_session, sample_record):
        """Test that negative order number returns False."""
        sample_record.order_number = -1
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is False
        assert sample_record.order_number == -1
    
    def test_different_ball_in_court_ignored(self, mock_db_session, sample_record):
        """Test that urgent submittals with different ball_in_court are ignored."""
        # Create urgent submittal with different ball_in_court
        other_urgent = Mock(spec=ProcoreSubmittal)
        other_urgent.order_number = 0.9
        other_urgent.submittal_id = "other_urgent"
        other_urgent.ball_in_court = "Drafter B"
        
        # Mock query to return empty (different ball_in_court filtered out)
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # Other urgent should not be affected
        assert other_urgent.order_number == 0.9
    
    def test_ladder_progression_example(self, mock_db_session, sample_record):
        """Test a realistic ladder progression scenario - 0.9 not occupied, so no shifting."""
        # Start with 2 urgent items at 0.7 and 0.8 (0.9 is available)
        urgent1 = Mock(spec=ProcoreSubmittal)
        urgent1.order_number = 0.7
        urgent1.submittal_id = "urgent_1"
        
        urgent2 = Mock(spec=ProcoreSubmittal)
        urgent2.order_number = 0.8
        urgent2.submittal_id = "urgent_2"
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            urgent1, urgent2
        ]
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # 0.9 is available, so no shifting needed
        assert urgent1.order_number == pytest.approx(0.7, abs=0.001)  # Stays 0.7
        assert urgent2.order_number == pytest.approx(0.8, abs=0.001)  # Stays 0.8
    
    def test_eight_slots_filled_09_available(self, mock_db_session, sample_record):
        """Test that when 8 slots filled (0.1-0.8), new gets 0.9 without shifting."""
        # Create 8 urgent submittals filling slots 0.1 through 0.8
        urgent_submittals = []
        for i in range(1, 9):  # 0.1 through 0.8
            urgent = Mock(spec=ProcoreSubmittal)
            urgent.order_number = i * 0.1
            urgent.submittal_id = f"urgent_{i}"
            urgent_submittals.append(urgent)
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = urgent_submittals
        
        result = _bump_order_number_to_decimal(sample_record, "submittal_123", "Drafter A")
        
        assert result is True
        assert sample_record.order_number == 0.9
        # 0.9 is available, so all existing urgent should remain unchanged
        for i, urgent in enumerate(urgent_submittals):
            assert urgent.order_number == pytest.approx((i + 1) * 0.1, abs=0.001)

