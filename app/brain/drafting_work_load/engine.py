"""
Pure business logic engine for Drafting Work Load operations.
Contains no database dependencies - works with plain data structures.
"""
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SubmittalOrderUpdate:
    """Value object representing a submittal order update operation."""
    submittal_id: str
    new_order: Optional[float]
    old_order: Optional[float]
    ball_in_court: Optional[str]


class DraftingWorkLoadEngine:
    """Pure business logic for Drafting Work Load operations."""
    
    # Valid statuses for submittal_drafting_status
    VALID_DRAFTING_STATUSES = ['', 'STARTED', 'NEED VIF', 'HOLD']
    
    @staticmethod
    def validate_notes(notes: Optional[str]) -> Optional[str]:
        """
        Validate and normalize notes.
        
        Args:
            notes: Raw notes input
            
        Returns:
            Normalized notes (None if empty, stripped string otherwise)
        """
        if notes is None:
            return None
        
        cleaned = str(notes).strip()
        return cleaned if cleaned else None
    
    @staticmethod
    def validate_drafting_status(status: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate submittal_drafting_status.
        
        Args:
            status: The status to validate
            
        Returns:
            (is_valid, normalized_status, error_message)
        """
        # None becomes empty string
        if status is None:
            return True, '', None
        
        # Check if valid
        if status not in DraftingWorkLoadEngine.VALID_DRAFTING_STATUSES:
            valid_display = ', '.join([s if s else '(blank)' 
                                      for s in DraftingWorkLoadEngine.VALID_DRAFTING_STATUSES])
            return False, None, f"submittal_drafting_status must be one of: {valid_display}"
        
        return True, status, None
    
    @staticmethod
    def validate_due_date(due_date: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate due date format.
        
        Args:
            due_date: The due date string to validate (ISO format: YYYY-MM-DD or None)
            
        Returns:
            (is_valid, normalized_date, error_message)
        """
        if due_date is None or due_date == '':
            return True, None, None
        
        # Check if it's a valid date string (YYYY-MM-DD format)
        try:
            from datetime import datetime
            # Try to parse the date
            parsed_date = datetime.strptime(due_date, '%Y-%m-%d').date()
            # Return as ISO format string
            return True, due_date, None
        except (ValueError, TypeError):
            return False, None, "due_date must be in YYYY-MM-DD format or empty"


class SubmittalOrderingEngine:
    """Pure business logic for submittal ordering calculations."""
    
    @staticmethod
    def safe_float_order(order_val) -> Optional[float]:
        """Convert order_number to float, handling None and string values."""
        if order_val is None:
            return None
        try:
            return float(order_val)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def validate_order_number(order_number: Optional[float]) -> Tuple[bool, Optional[str]]:
        """
        Validate order number.
        - NULL is allowed (clears order number)
        - Must be > 0
        - If < 1 (urgency slot), must be exactly one of: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9
        - If >= 1, any integer or decimal is allowed
        
        Returns: (is_valid, error_message)
        """
        if order_number is None:
            return True, None
        
        try:
            order_float = float(order_number)
            if order_float == 0:
                return False, "order_number cannot be 0"
            
            # If it's an urgency slot (0 < order < 1), it must be exactly one of the 9 slots
            if 0 < order_float < 1:
                # Round to nearest tenth to check if it's a valid slot
                rounded = round(order_float, 1)
                valid_urgency_slots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
                if rounded not in valid_urgency_slots:
                    return False, f"Urgency slots must be exactly 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, or 0.9. Got: {order_float}"
                # If it's close to a valid slot but not exact, round it
                if abs(order_float - rounded) > 0.001:  # Allow small floating point errors
                    return False, f"Urgency slots must be exactly 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, or 0.9. Got: {order_float}"
            
            return True, None
        except (ValueError, TypeError):
            return False, "order_number must be a valid number"
    
    @staticmethod
    def categorize_submittals(submittals_data: List[Dict], exclude_id: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Categorize submittals into urgent (0 < order < 1) and regular (order >= 1).
        Excludes the submittal being updated and NULL values.
        
        Args:
            submittals_data: List of dicts with 'submittal_id' and 'order_number' keys
            exclude_id: Submittal ID to exclude from categorization
            
        Returns: (urgent_submittals, regular_submittals)
        """
        urgent = []
        regular = []
        
        for s in submittals_data:
            if s.get('submittal_id') == exclude_id:
                continue
            
            order_val = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
            if order_val is not None:
                if 0 < order_val < 1:
                    urgent.append(s)
                elif order_val >= 1:
                    regular.append(s)

        # Sort by current order
        urgent.sort(key=lambda s: SubmittalOrderingEngine.safe_float_order(s.get('order_number')) or 0)
        regular.sort(key=lambda s: SubmittalOrderingEngine.safe_float_order(s.get('order_number')) or 0)
        
        return urgent, regular

    @staticmethod
    def handle_set_to_null(submittal_data: Dict, all_group_submittals_data: List[Dict]) -> List[Tuple[str, Optional[float]]]:
        """
        Handle setting order to NULL. Returns list of (submittal_id, new_order_value) tuples.
        Compresses urgency submittals (0 < order < 1) upward when one is removed.
        Ordered submittals (>= 1) keep their absolute order numbers (no cascade).

        Args:
            submittal_data: Dict with 'submittal_id' and 'order_number' keys
            all_group_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples
        """
        old_order = SubmittalOrderingEngine.safe_float_order(submittal_data.get('order_number'))
        updates = []

        if old_order is not None and 0 < old_order < 1:
            # Urgency submittal: compress remaining urgency submittals upward (toward 0.9)
            for s in all_group_submittals_data:
                if s.get('submittal_id') == submittal_data.get('submittal_id'):
                    continue

                s_order = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
                if s_order is not None and 0 < s_order < 1:
                    if s_order < old_order:
                        # Shift urgency submittals with order < old_order up by 0.1 to fill gap
                        new_order = round(s_order + 0.1, 1)
                        updates.append((s.get('submittal_id'), new_order))
                    else:
                        # Include urgency submittals with order >= old_order (they stay the same)
                        updates.append((s.get('submittal_id'), s_order))
        # Ordered submittals (>= 1): no cascade — they keep their absolute order numbers

        # Update the target submittal
        updates.append((submittal_data.get('submittal_id'), None))
        return updates

    @staticmethod
    def handle_set_to_urgent(submittal_data: Dict, new_order: float, all_group_submittals_data: List[Dict]) -> List[Tuple[str, float]]:
        """
        Handle setting order to urgent (0 < order < 1). Returns list of (submittal_id, new_order_value) tuples.
        
        Stack/FIFO behavior: Position determines urgency, slots compress to fill from bottom (0.1, 0.2, 0.3...)
        After assignment, all urgency slots are compressed to fill gaps.
        
        Args:
            submittal_data: Dict with 'submittal_id' and 'order_number' keys
            new_order: New urgent order value (0 < new_order < 1)
            all_group_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys
            
        Returns: List of (submittal_id, new_order_value) tuples
        """
        old_order = SubmittalOrderingEngine.safe_float_order(submittal_data.get('order_number'))
        updates = []
        
        # Round urgency slot to nearest tenth place to ensure exact values (0.1, 0.2, ..., 0.9)
        rounded_order = round(new_order, 1)
        
        # Ordered submittals (>= 1) keep their absolute order numbers when item leaves — no cascade

        # Update the target submittal to new urgent value (rounded to tenth place)
        updates.append((submittal_data.get('submittal_id'), rounded_order))
        
        # Compress all urgency slots: sort by order (oldest/most urgent first) and reassign from 0.9 downward
        # Oldest (most urgent) gets lowest slot, newest (least urgent) gets 0.9
        # Example: 3 items → [0.7, 0.8, 0.9] where oldest is at 0.7, newest at 0.9
        urgent_submittals = []
        for s in all_group_submittals_data:
            # Use the new order if this is the submittal being updated, otherwise use current order
            if s.get('submittal_id') == submittal_data.get('submittal_id'):
                s_order = rounded_order
            else:
                s_order = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
            
            if s_order is not None and 0 < s_order < 1:
                urgent_submittals.append((s, s_order))
        
        # Sort by order (ascending: lower = older/more urgent, been waiting longer)
        urgent_submittals.sort(key=lambda x: x[1])
        
        # Reassign slots: compress DOWN to 0.9 (fill from highest slot downward)
        # Position 0 (oldest/most urgent) → highest slot - count + 1
        # Position N (newest/least urgent) → 0.9
        valid_urgency_slots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        total_urgent = len(urgent_submittals)
        
        for idx, (s, current_order) in enumerate(urgent_submittals):
            # Calculate slot index: newest (last in sorted list) gets 0.9, oldest gets (0.9 - count + 1)
            # idx 0 (oldest) → slot index (9 - total_urgent), idx (total_urgent-1) (newest) → slot index 8 (0.9)
            slot_index = (len(valid_urgency_slots) - total_urgent) + idx
            if 0 <= slot_index < len(valid_urgency_slots):
                new_slot = valid_urgency_slots[slot_index]
                # Only update if the slot has changed (avoid duplicate updates)
                if abs(current_order - new_slot) > 0.001:
                    # Check if this submittal is already in updates
                    already_updated = False
                    update_index = -1
                    for i, (update_id, update_order) in enumerate(updates):
                        if update_id == s.get('submittal_id'):
                            already_updated = True
                            update_index = i
                            break
                    
                    if not already_updated:
                        updates.append((s.get('submittal_id'), new_slot))
                    else:
                        # Update the existing update entry
                        updates[update_index] = (s.get('submittal_id'), new_slot)
        
        return updates

    @staticmethod
    def handle_set_to_regular(submittal_data: Dict, new_order: float, all_group_submittals_data: List[Dict]) -> List[Tuple[str, float]]:
        """
        Handle setting order to regular position (>= 1). Returns list of (submittal_id, new_order_value) tuples.
        Assigns the exact given order_number; does NOT renumber other ordered items.

        Args:
            submittal_data: Dict with 'submittal_id' and 'order_number' keys
            new_order: New regular order value (>= 1)
            all_group_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples
        """
        # Direct assign — no renumbering of other ordered items
        return [(submittal_data.get('submittal_id'), float(new_order))]

    @staticmethod
    def compress_orders(all_group_submittals_data: List[Dict]) -> List[Tuple[str, float]]:
        """
        Compress order numbers for urgency submittals only.
        - Urgency subset (0 < order < 1): Compresses down to 0.9 (fills from highest slot downward)
          Oldest (lowest order) gets the lowest available slot, newest (highest order) gets 0.9
        - Regular subset (order >= 1): Untouched — preserves absolute order numbers

        Args:
            all_group_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples for submittals that need updates
        """
        updates = []

        urgent = []
        for s in all_group_submittals_data:
            order_val = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
            if order_val is not None and 0 < order_val < 1:
                urgent.append(s)

        # Sort urgent by current order (ascending: oldest/most urgent first)
        urgent.sort(key=lambda s: SubmittalOrderingEngine.safe_float_order(s.get('order_number')) or 0)

        # Compress urgency slots: fill from 0.9 downward
        valid_urgency_slots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        total_urgent = len(urgent)

        for idx, s in enumerate(urgent):
            slot_index = (len(valid_urgency_slots) - total_urgent) + idx
            if 0 <= slot_index < len(valid_urgency_slots):
                new_slot = valid_urgency_slots[slot_index]
                current_order = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
                if current_order is None or abs(current_order - new_slot) > 0.001:
                    updates.append((s.get('submittal_id'), new_slot))

        return updates

    @staticmethod
    def compress_ordered_submittals(all_group_submittals_data: List[Dict]) -> List[Tuple[str, float]]:
        """
        Compress ordered (>= 1) submittals to sequential integers starting at 1.
        Preserves relative order. Urgency submittals (0 < order < 1) are untouched.
        Example: [4, 5, 6, 7, 8] → [1, 2, 3, 4, 5]
        Returns: List of (submittal_id, new_order_value) tuples for submittals that need updates.
        """
        ordered = [
            s for s in all_group_submittals_data
            if (v := SubmittalOrderingEngine.safe_float_order(s.get('order_number'))) is not None and v >= 1
        ]
        ordered.sort(key=lambda s: SubmittalOrderingEngine.safe_float_order(s.get('order_number')) or 0)
        updates = []
        for idx, s in enumerate(ordered):
            new_order = float(idx + 1)
            current = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
            if current is None or abs(current - new_order) > 0.001:
                updates.append((s.get('submittal_id'), new_order))
        return updates

    @staticmethod
    def calculate_step_updates(submittal_data: Dict, direction: str, all_group_submittals_data: List[Dict]) -> List[Tuple[str, float]]:
        """
        Calculate a simple 2-item swap for stepping up or down within the same zone.
        Zones are independent: urgent (0 < order < 1) and ordered (>= 1).
        Unordered (null) items cannot be stepped.

        Args:
            submittal_data: Dict with 'submittal_id' and 'order_number' keys
            direction: 'up' (toward lower order number) or 'down' (toward higher order number)
            all_group_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples (2 items — the swap)
        """
        submittal_id = submittal_data.get('submittal_id')
        current_order = SubmittalOrderingEngine.safe_float_order(submittal_data.get('order_number'))

        if current_order is None:
            raise ValueError("Cannot step an unordered (null) submittal")

        is_urgent = 0 < current_order < 1
        is_regular = current_order >= 1

        if not is_urgent and not is_regular:
            raise ValueError(f"Invalid order number for step: {current_order}")

        # Collect same-zone neighbours (excluding target)
        same_zone = []
        for s in all_group_submittals_data:
            if s.get('submittal_id') == submittal_id:
                continue
            s_order = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
            if s_order is None:
                continue
            if is_urgent and 0 < s_order < 1:
                same_zone.append(s)
            elif is_regular and s_order >= 1:
                same_zone.append(s)

        same_zone.sort(key=lambda s: SubmittalOrderingEngine.safe_float_order(s.get('order_number')) or 0)

        if direction == 'up':
            candidates = [s for s in same_zone
                          if (SubmittalOrderingEngine.safe_float_order(s.get('order_number')) or 0) < current_order]
            if not candidates:
                raise ValueError("Already at top of zone, cannot step up")
            adjacent = candidates[-1]  # largest order less than current
        elif direction == 'down':
            candidates = [s for s in same_zone
                          if (SubmittalOrderingEngine.safe_float_order(s.get('order_number')) or 0) > current_order]
            if not candidates:
                raise ValueError("Already at bottom of zone, cannot step down")
            adjacent = candidates[0]  # smallest order greater than current
        else:
            raise ValueError(f"Invalid direction: {direction}")

        adjacent_order = SubmittalOrderingEngine.safe_float_order(adjacent.get('order_number'))
        adjacent_id = adjacent.get('submittal_id')

        # Swap the two order numbers
        return [
            (submittal_id, adjacent_order),
            (adjacent_id, current_order),
        ]

    @staticmethod
    def calculate_updates(update_request: SubmittalOrderUpdate, all_group_submittals_data: List[Dict]) -> List[Tuple[str, Optional[float]]]:
        """
        Calculate all submittal updates needed for the requested change.

        Args:
            update_request: SubmittalOrderUpdate value object
            all_group_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples
        """
        submittal_data = next(
            (s for s in all_group_submittals_data if s.get('submittal_id') == update_request.submittal_id),
            None
        )

        if not submittal_data:
            raise ValueError(f"Submittal {update_request.submittal_id} not found in group")

        new_order = update_request.new_order

        if new_order is None:
            return SubmittalOrderingEngine.handle_set_to_null(submittal_data, all_group_submittals_data)
        elif new_order < 1:
            return SubmittalOrderingEngine.handle_set_to_urgent(submittal_data, new_order, all_group_submittals_data)
        else:
            return SubmittalOrderingEngine.handle_set_to_regular(submittal_data, new_order, all_group_submittals_data)

    @staticmethod
    def calculate_drag_to_ordered(dragged_data: Dict, target_order: Optional[float], all_submittals_data: List[Dict]) -> List[Tuple[str, Optional[float]]]:
        """
        Handle drag to ordered zone. Dragged row takes the target row's order number;
        all rows at >= target order (excluding dragged) shift +1. If dragged row came
        from urgency zone, apply urgency compression to remaining urgency items.

        Args:
            dragged_data: Dict with 'submittal_id' and 'order_number' keys
            target_order: Order number of row being displaced (exact float value), or None to append to end
            all_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples
        """
        updates = []
        dragged_id = dragged_data.get('submittal_id')
        old_order = SubmittalOrderingEngine.safe_float_order(dragged_data.get('order_number'))

        if target_order is None:
            # Append to end: max(ordered orders) + 1
            ordered = [
                SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
                for s in all_submittals_data
                if s.get('submittal_id') != dragged_id and
                (v := SubmittalOrderingEngine.safe_float_order(s.get('order_number'))) is not None and v >= 1
            ]
            new_order_for_dragged = float(max(ordered) + 1) if ordered else 1.0
            updates.append((dragged_id, new_order_for_dragged))
        else:
            # Insert before target: dragged gets target_order, all >= target shift +1
            new_order_for_dragged = target_order
            updates.append((dragged_id, new_order_for_dragged))

            # Shift all ordered items with order >= target (excluding dragged) up by 1
            for s in all_submittals_data:
                if s.get('submittal_id') == dragged_id:
                    continue
                s_order = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
                if s_order is not None and s_order >= target_order:
                    new_order = s_order + 1
                    updates.append((s.get('submittal_id'), new_order))

        # If dragged row came from urgency, compress remaining urgency items
        if old_order is not None and 0 < old_order < 1:
            # Use handle_set_to_null logic to compress urgency
            urgency_updates = SubmittalOrderingEngine.handle_set_to_null(
                {'submittal_id': dragged_id, 'order_number': old_order},
                all_submittals_data
            )
            # Remove the dragged row's null update and merge urgency compression
            for submittal_id, new_order in urgency_updates:
                if submittal_id != dragged_id:
                    # Check if this submittal is already in updates (don't duplicate)
                    if not any(uid == submittal_id for uid, _ in updates):
                        updates.append((submittal_id, new_order))

        return updates

    @staticmethod
    def calculate_drag_to_urgent(dragged_data: Dict, all_submittals_data: List[Dict]) -> List[Tuple[str, Optional[float]]]:
        """
        Handle drag to urgent zone. New item gets 0.9. Uses adaptive shift logic:
        only shifts items that need to move to make room for 0.9 (unlike handle_set_to_urgent
        which re-sorts all urgency items from scratch).

        Args:
            dragged_data: Dict with 'submittal_id' and 'order_number' keys
            all_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples
        """
        updates = []
        dragged_id = dragged_data.get('submittal_id')

        # New item gets 0.9
        new_order_for_dragged = 0.9
        updates.append((dragged_id, new_order_for_dragged))

        # Check if 0.9 is occupied
        existing_urgent = [
            SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
            for s in all_submittals_data
            if s.get('submittal_id') != dragged_id and
            (v := SubmittalOrderingEngine.safe_float_order(s.get('order_number'))) is not None and
            0 < v < 1
        ]

        slot_09_occupied = 0.9 in existing_urgent

        if not slot_09_occupied:
            # 0.9 is available, no shifts needed
            pass
        elif len(existing_urgent) < 9:
            # 0.9 occupied but slots available: find highest available below 0.9, shift only items above it
            all_slots = set([round(i * 0.1, 1) for i in range(1, 10)])
            occupied_slots = set(existing_urgent)
            available_below_09 = [s for s in sorted(all_slots - occupied_slots, reverse=True) if s < 0.9]

            if available_below_09:
                highest_available = available_below_09[0]
                # Shift only items > highest_available down by 0.1
                for s in all_submittals_data:
                    if s.get('submittal_id') == dragged_id:
                        continue
                    s_order = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
                    if s_order is not None and 0 < s_order < 1 and s_order > highest_available:
                        new_order = round(s_order - 0.1, 1)
                        updates.append((s.get('submittal_id'), new_order))
        else:
            # All 9 slots filled: new item gets 1.0, all regular orders shift +1
            updates[-1] = (dragged_id, 1.0)  # Update dragged to 1.0
            for s in all_submittals_data:
                if s.get('submittal_id') == dragged_id:
                    continue
                s_order = SubmittalOrderingEngine.safe_float_order(s.get('order_number'))
                if s_order is not None and s_order >= 1:
                    new_order = s_order + 1
                    updates.append((s.get('submittal_id'), new_order))

        return updates

    @staticmethod
    def calculate_drag_to_unordered(dragged_data: Dict, all_submittals_data: List[Dict]) -> List[Tuple[str, Optional[float]]]:
        """
        Handle drag to unordered zone. Equivalent to handle_set_to_null.

        Args:
            dragged_data: Dict with 'submittal_id' and 'order_number' keys
            all_submittals_data: List of dicts with 'submittal_id' and 'order_number' keys

        Returns: List of (submittal_id, new_order_value) tuples
        """
        return SubmittalOrderingEngine.handle_set_to_null(dragged_data, all_submittals_data)


class UrgencyEngine:
    """Pure business logic for urgency-related operations."""

    @staticmethod
    def calculate_bump_unordered_updates(existing_regular_submittals_data: List[Dict]) -> float:
        """
        Calculate the new order_number for bumping an unordered (null) submittal to the ordered list.
        Appends to the end: max(existing integer orders) + 1, or 1 if none exist.

        Args:
            existing_regular_submittals_data: List of dicts with 'submittal_id' and 'order_number' for
                                              ordered (>= 1) submittals in the same ball_in_court group

        Returns:
            new_order: float — the order number to assign
        """
        existing_orders = []
        for s in existing_regular_submittals_data:
            order_val = s.get('order_number')
            if order_val is not None:
                try:
                    f = float(order_val)
                    if f >= 1:
                        existing_orders.append(f)
                except (ValueError, TypeError):
                    pass

        if existing_orders:
            return float(int(max(existing_orders))) + 1.0
        return 1.0

    @staticmethod
    def check_submitter_pending_in_workflow(approvers: List[Dict]) -> bool:
        """
        Check if the submitter (workflow_group_number 0) appears as a pending approver
        in the next workflow group that has pending approvers.
        The "next workflow group" is determined by finding the workflow group with the
        smallest workflow_group_number > 0 that has at least one pending approver.
        Only checks the next pending approver in line for urgency bump functionality.
        
        Args:
            approvers: List of approver dictionaries from submittal data
            
        Returns:
            bool: True if submitter appears as pending in the next workflow group with pending approvers
        """
        if not approvers or not isinstance(approvers, list):
            return False
        
        # Find the submitter (workflow_group_number 0)
        submitter = None
        for approver in approvers:
            if not isinstance(approver, dict):
                continue
            workflow_group = approver.get("workflow_group_number")
            
            if workflow_group == 0:
                user = approver.get("user")
                if user and isinstance(user, dict):
                    submitter = {
                        "name": user.get("name"),
                        "login": user.get("login")
                    }
                break
        
        if not submitter:
            return False
        
        # Find the next workflow group that has at least one pending approver
        # First, collect all workflow groups > 0 that have pending approvers
        pending_workflow_groups = set()
        for approver in approvers:
            if not isinstance(approver, dict):
                continue
            
            workflow_group = approver.get("workflow_group_number")
            if workflow_group is None or workflow_group == 0:
                continue  # Skip submitter or approvers without workflow_group_number
            
            # Check if this approver is pending
            response = approver.get("response", {})
            if isinstance(response, dict):
                response_name = response.get("name", "").strip()
                if response_name.lower() == "pending":
                    pending_workflow_groups.add(workflow_group)
        
        if not pending_workflow_groups:
            return False
        
        # Find the minimum workflow group number (the next one in line)
        next_workflow_group = min(pending_workflow_groups)
        
        # Check if submitter appears as pending in the NEXT workflow group only
        for approver in approvers:
            if not isinstance(approver, dict):
                continue
            
            workflow_group = approver.get("workflow_group_number")
            # Only check approvers in the next workflow group
            if workflow_group != next_workflow_group:
                continue
            
            # Check if response is "Pending"
            response = approver.get("response", {})
            if not isinstance(response, dict):
                continue
            
            response_name = response.get("name", "").strip()
            if response_name.lower() != "pending":
                continue
            
            # Check if user matches submitter
            user = approver.get("user")
            if not user or not isinstance(user, dict):
                continue
            
            approver_name = user.get("name")
            approver_login = user.get("login")
            
            # Match by name or login
            name_match = (submitter.get("name") and approver_name and 
                         submitter.get("name").lower() == approver_name.lower())
            login_match = (submitter.get("login") and approver_login and 
                          submitter.get("login").lower() == approver_login.lower())
            
            if name_match or login_match:
                return True
        
        # No match found in the next workflow group
        return False
    
    @staticmethod
    def calculate_bump_updates(
        current_order: float,
        existing_urgent_submittals_data: List[Dict],
        existing_regular_submittals_data: List[Dict]
    ) -> Tuple[bool, Optional[float], List[Tuple[str, float]], List[Tuple[str, float]]]:
        """
        Calculate updates needed for bumping a submittal to urgent.
        
        Args:
            current_order: Current order number of the submittal being bumped (must be >= 1)
            existing_urgent_submittals_data: List of dicts with 'submittal_id' and 'order_number' for urgent submittals
            existing_regular_submittals_data: List of dicts with 'submittal_id' and 'order_number' for regular submittals
            
        Returns:
            Tuple of:
            - can_bump: bool (True if bump is valid)
            - new_order_for_bumped: Optional[float] (new order for the bumped submittal)
            - urgent_updates: List[Tuple[str, float]] (list of (submittal_id, new_order) for urgent shifts)
            - regular_updates: List[Tuple[str, float]] (list of (submittal_id, new_order) for regular shifts)
        """
        # Check if order_number is an integer >= 1
        is_integer = isinstance(current_order, (int, float)) and current_order >= 1 and current_order == int(current_order)
        
        if not is_integer:
            return False, None, [], []
        
        existing_urgent_orders = [
            float(s.get('order_number')) 
            for s in existing_urgent_submittals_data 
            if s.get('order_number') is not None
        ]
        
        # Check if 0.9 is already occupied
        slot_09_occupied = 0.9 in existing_urgent_orders
        
        # Check if all 9 slots are filled (0.1 through 0.9)
        has_all_slots_filled = len(existing_urgent_submittals_data) >= 9
        
        # Ladder system logic
        urgent_updates = []
        regular_updates = []
        
        if has_all_slots_filled:
            # All 9 slots are filled - new urgent gets order 1, regular orders shift up
            new_order_for_bumped = 1.0
            # Shift all regular orders UP by 1 (1 -> 2, 2 -> 3, etc.)
            for s in existing_regular_submittals_data:
                old_order = float(s.get('order_number'))
                new_order = old_order + 1  # Shift UP means higher numbers (less urgent)
                regular_updates.append((s.get('submittal_id'), new_order))
        elif not slot_09_occupied:
            # 0.9 is available - just assign it to new submittal, no need to shift existing ones
            new_order_for_bumped = 0.9
        else:
            # 0.9 is occupied but not all slots filled - need to shift existing urgent submittals down to make room
            # Find available slots and only shift items that need to move to fill gaps
            all_slots = set([round(i * 0.1, 1) for i in range(1, 10)])  # {0.1, 0.2, ..., 0.9}
            occupied_slots = set(existing_urgent_orders)
            available_slots = sorted(all_slots - occupied_slots, reverse=True)  # Sort descending
            
            new_order_for_bumped = 0.9
            
            if available_slots:
                # Find the highest available slot below 0.9
                highest_available_below_09 = max([s for s in available_slots if s < 0.9], default=None)
                
                if highest_available_below_09 is not None:
                    # Only shift items at positions > highest_available_below_09
                    # Sort existing urgent submittals by order (descending) to process from highest to lowest
                    sorted_urgent = sorted(existing_urgent_submittals_data, 
                                          key=lambda s: float(s.get('order_number')), 
                                          reverse=True)
                    
                    for submittal_data in sorted_urgent:
                        old_order = float(submittal_data.get('order_number'))
                        # Only shift items that are above the highest available slot
                        if old_order > highest_available_below_09:
                            # This item needs to shift down to make room
                            new_order = old_order - 0.1  # Shift DOWN toward 0.1 (most urgent)
                            
                            if new_order < 0.1:
                                # This shouldn't happen if we're managing slots correctly, but handle edge case
                                logger.error(f"calculate_bump_updates: new_order {new_order} < 0.1, capping at 0.1")
                                new_order = 0.1
                            else:
                                # Round to nearest tenth place to ensure exact values (0.1, 0.2, ..., 0.9)
                                new_order = round(new_order, 1)
                            urgent_updates.append((submittal_data.get('submittal_id'), new_order))
                else:
                    # No available slots below 0.9 - fall back to shifting all items
                    sorted_urgent = sorted(existing_urgent_submittals_data, 
                                          key=lambda s: float(s.get('order_number')))
                    for submittal_data in sorted_urgent:
                        old_order = float(submittal_data.get('order_number'))
                        new_order = old_order - 0.1
                        if new_order < 0.1:
                            new_order = 0.1
                        else:
                            new_order = round(new_order, 1)
                        urgent_updates.append((submittal_data.get('submittal_id'), new_order))
            else:
                # No available slots - this shouldn't happen if not all slots are filled, but handle edge case
                sorted_urgent = sorted(existing_urgent_submittals_data, 
                                      key=lambda s: float(s.get('order_number')))
                for submittal_data in sorted_urgent:
                    old_order = float(submittal_data.get('order_number'))
                    new_order = old_order - 0.1
                    if new_order < 0.1:
                        new_order = 0.1
                    else:
                        new_order = round(new_order, 1)
                    urgent_updates.append((submittal_data.get('submittal_id'), new_order))
        
        return True, new_order_for_bumped, urgent_updates, regular_updates


class LocationEngine:
    """Pure geometry/boundary logic for job site location. No database dependencies."""

    # Meters: include job_sites where user is within this distance of the site geometry (PostGIS only)
    LOCATION_BUFFER_METERS = 25

    @staticmethod
    def point_in_polygon(lng: float, lat: float, coordinates: list) -> bool:
        """
        Ray-casting test. coordinates is GeoJSON Polygon coordinates: list of rings; first ring is exterior.
        Each ring is list of [lng, lat] (or [lng, lat, z]). Returns True if (lng, lat) is inside the polygon.
        """
        if not coordinates or not coordinates[0]:
            return False
        ring = coordinates[0]
        n = len(ring)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside
