# dwl_ordering.py
"""
Business logic for Drafting Work Load ordering, separated from HTTP layer for easier testing.
"""
from datetime import datetime
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class SubmittalOrderUpdate:
    """Value object representing a submittal order update operation."""
    submittal_id: str
    new_order: Optional[float]
    old_order: Optional[float]
    ball_in_court: Optional[str]

class SubmittalOrderingService:
    """Handles the business logic for submittal ordering."""
    
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
        Returns: (is_valid, error_message)
        """
        if order_number is None:
            return True, None
        
        try:
            order_float = float(order_number)
            if order_float == 0:
                return False, "order_number cannot be 0"
            return True, None
        except (ValueError, TypeError):
            return False, "order_number must be a valid number"
    
    @staticmethod
    def categorize_submittals(submittals: List, exclude_id: str) -> Tuple[List, List]:
        """
        Categorize submittals into urgent (0 < order < 1) and regular (order >= 1).
        Excludes the submittal being updated and NULL values.
        
        Returns: (urgent_submittals, regular_submittals)
        """
        urgent = []
        regular = []
        
        for s in submittals:
            if s.submittal_id == exclude_id:
                continue
            
            order_val = SubmittalOrderingService.safe_float_order(s.order_number)
            if order_val is not None:
                if 0 < order_val < 1:
                    urgent.append(s)
                elif order_val >= 1:
                    regular.append(s)

        # Sort by current order
        urgent.sort(key=lambda s: SubmittalOrderingService.safe_float_order(s.order_number) or 0)
        regular.sort(key=lambda s: SubmittalOrderingService.safe_float_order(s.order_number) or 0)
        
        return urgent, regular

    @staticmethod
    def handle_set_to_null(submittal, all_group_submittals: List) -> List:
        """
        Handle setting order to NULL. Returns list of submittals that need updates.
        """
        old_order = SubmittalOrderingService.safe_float_order(submittal.order_number)
        updates = []
        
        # Only renumber if old value was >= 1
        if old_order is not None and old_order >= 1:
            for s in all_group_submittals:
                if s.submittal_id == submittal.submittal_id:
                    continue
                
                s_order = SubmittalOrderingService.safe_float_order(s.order_number)
                # Decrease order numbers > old_order by 1 (only for values >= 1)
                if s_order is not None and s_order >= 1 and s_order > old_order:
                    updates.append((s, s_order - 1))
        
        # Update the target submittal
        updates.append((submittal, None))
        return updates

    @staticmethod
    def handle_set_to_urgent(submittal, new_order: float, all_group_submittals: List) -> List:
        """
        Handle setting order to urgent (0 < order < 1). Returns list of submittals that need updates.
        """
        old_order = SubmittalOrderingService.safe_float_order(submittal.order_number)
        updates = []
        
        # If old value was >= 1, renumber those greater than old value
        if old_order is not None and old_order >= 1:
            for s in all_group_submittals:
                if s.submittal_id == submittal.submittal_id:
                    continue
                
                s_order = SubmittalOrderingService.safe_float_order(s.order_number)
                if s_order is not None and s_order >= 1 and s_order > old_order:
                    updates.append((s, s_order - 1))
        
        # Update the target submittal to new urgent value
        updates.append((submittal, new_order))
        return updates

    @staticmethod
    def handle_set_to_regular(submittal, new_order: float, all_group_submittals: List) -> List:
        """
        Handle setting order to regular position (>= 1). Returns list of submittals that need updates.
        Renumbers all regular positions to be tight (1, 2, 3...), preserves urgent decimals.
        """
        urgent, regular = SubmittalOrderingService.categorize_submittals(
            all_group_submittals, 
            submittal.submittal_id
        )
        
        # Insert submittal at target position
        target_pos = int(new_order) - 1  # Convert to 0-based
        target_pos = max(0, min(target_pos, len(regular)))
        
        reordered_regular = regular[:target_pos] + [submittal] + regular[target_pos:]
        
        # Build updates list
        updates = []
        
        # Urgent submittals keep their values (no updates needed for them)
        # Regular submittals get renumbered to 1, 2, 3...
        next_integer = 1
        for row in reordered_regular:
            updates.append((row, float(next_integer)))
            next_integer += 1
        
        return updates

    @staticmethod
    def calculate_updates(update_request: SubmittalOrderUpdate, all_group_submittals: List) -> List:
        """
        Calculate all submittal updates needed for the requested change.
        Returns: List of (submittal, new_order_value) tuples
        """
        submittal = next(
            (s for s in all_group_submittals if s.submittal_id == update_request.submittal_id),
            None
        )
        
        if not submittal:
            raise ValueError(f"Submittal {update_request.submittal_id} not found in group")
        
        new_order = update_request.new_order
        
        if new_order is None:
            return SubmittalOrderingService.handle_set_to_null(submittal, all_group_submittals)
        elif new_order < 1:
            return SubmittalOrderingService.handle_set_to_urgent(submittal, new_order, all_group_submittals)
        else:
            return SubmittalOrderingService.handle_set_to_regular(submittal, new_order, all_group_submittals)