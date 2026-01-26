# dwl_ordering.py
"""
Service layer for Drafting Work Load operations.
Consolidates all DWL business logic for easier testing and maintenance.
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

class DraftingWorkLoadService:
    """Service for Drafting Work Load operations."""
    
    # Valid statuses for submittal_drafting_status
    VALID_DRAFTING_STATUSES = ['', 'STARTED', 'NEED VIF', 'HOLD']
    
    @staticmethod
    def get_open_submittals(submittal_model):
        """
        Get all submittals with status='Open'.
        
        Args:
            submittal_model: The ProcoreSubmittal model class
            
        Returns:
            List of submittals with status='Open'
        """
        return submittal_model.query.filter(
            submittal_model.status == 'Open'
        ).all()
    
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
        if status not in DraftingWorkLoadService.VALID_DRAFTING_STATUSES:
            valid_display = ', '.join([s if s else '(blank)' 
                                      for s in DraftingWorkLoadService.VALID_DRAFTING_STATUSES])
            return False, None, f"submittal_drafting_status must be one of: {valid_display}"
        
        return True, status, None
    
    @staticmethod
    def update_notes(submittal, notes: Optional[str]) -> None:
        """
        Update submittal notes.
        
        Args:
            submittal: The submittal object to update
            notes: New notes value
        
        Note: Does not update last_updated to preserve ordering for unordered submittals.
        Only order_number and submittal_drafting_status updates should change last_updated.
        """
        validated_notes = DraftingWorkLoadService.validate_notes(notes)
        submittal.notes = validated_notes
        # Do NOT update last_updated here - notes changes should not affect submittal ordering
    
    @staticmethod
    def update_drafting_status(submittal, status: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Update submittal drafting status.
        
        Args:
            submittal: The submittal object to update
            status: New status value
            
        Returns:
            (success, error_message)
        """
        is_valid, normalized_status, error = DraftingWorkLoadService.validate_drafting_status(status)
        
        if not is_valid:
            return False, error
        
        submittal.submittal_drafting_status = normalized_status
        submittal.last_updated = datetime.utcnow()
        return True, None

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
    
    @staticmethod
    def reorder_group_to_start_from_one(all_group_submittals: List) -> List:
        """
        Reorder all items in a group so that the lowest order_number >= 1 becomes 1,
        and all subsequent items are renumbered sequentially (2, 3, 4...) while preserving
        their relative order. Ignores decimal values (0 < order < 1) and NULL values.
        
        Example: If group has items with orders [11, 12, 13, 14], they become [1, 2, 3, 4].
        The item with order 11 (lowest) becomes 1, 12 becomes 2, etc.
        
        Args:
            all_group_submittals: List of all submittals in the same ball_in_court group
            
        Returns:
            List of (submittal, new_order_value) tuples for items that need updates
        """
        updates = []
        
        # Step 1: Get all items with order_number >= 1 (ignore decimals and NULL)
        regular_items = []
        for s in all_group_submittals:
            order_val = SubmittalOrderingService.safe_float_order(s.order_number)
            if order_val is not None and order_val >= 1:
                regular_items.append(s)
        
        # Step 2: Sort by current order number (ascending) to find the lowest
        # This ensures the lowest order number will be first in the list
        regular_items.sort(key=lambda s: SubmittalOrderingService.safe_float_order(s.order_number) or 0)
        
        # If no items to reorder, return empty list
        if not regular_items:
            return updates
        
        # Step 3: Renumber sequentially starting from 1, preserving relative order
        # The first item (lowest order) becomes 1, second becomes 2, etc.
        new_order = 1
        for submittal in regular_items:
            old_order = SubmittalOrderingService.safe_float_order(submittal.order_number)
            # Only add to updates if the order actually changes
            if old_order != new_order:
                updates.append((submittal, float(new_order)))
            new_order += 1
        
        return updates