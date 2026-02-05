"""
Service layer for Drafting Work Load operations.
Handles database operations and coordinates with engine for business logic.
"""
from datetime import datetime
from typing import Optional, List, Tuple
import logging
from app.models import db, ProcoreSubmittal
from app.brain.drafting_work_load.engine import (
    DraftingWorkLoadEngine,
    SubmittalOrderingEngine,
    UrgencyEngine,
    SubmittalOrderUpdate
)

# Re-export SubmittalOrderUpdate for backward compatibility
__all__ = ['DraftingWorkLoadService', 'SubmittalOrderingService', 'UrgencyService', 'SubmittalOrderUpdate']

logger = logging.getLogger(__name__)


class DraftingWorkLoadService:
    """Service for Drafting Work Load operations."""
    
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
        return DraftingWorkLoadEngine.validate_notes(notes)
    
    @staticmethod
    def validate_drafting_status(status: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate submittal_drafting_status.
        
        Args:
            status: The status to validate
            
        Returns:
            (is_valid, normalized_status, error_message)
        """
        return DraftingWorkLoadEngine.validate_drafting_status(status)
    
    @staticmethod
    def update_notes(submittal, notes: Optional[str]) -> None:
        """
        Update submittal notes.
        
        Args:
            submittal: The submittal object to update
            notes: New notes value
        """
        validated_notes = DraftingWorkLoadEngine.validate_notes(notes)
        submittal.notes = validated_notes
        submittal.last_updated = datetime.utcnow()
        logger.info(f"Updated notes for submittal {submittal.submittal_id}")
    
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
        is_valid, normalized_status, error = DraftingWorkLoadEngine.validate_drafting_status(status)
        
        if not is_valid:
            logger.warning(f"Invalid drafting status for submittal {submittal.submittal_id}: {error}")
            return False, error
        
        submittal.submittal_drafting_status = normalized_status
        submittal.last_updated = datetime.utcnow()
        logger.info(f"Updated drafting status for submittal {submittal.submittal_id} to '{normalized_status}'")
        return True, None


class SubmittalOrderingService:
    """Service for submittal ordering operations."""
    
    @staticmethod
    def safe_float_order(order_val) -> Optional[float]:
        """Convert order_number to float, handling None and string values."""
        return SubmittalOrderingEngine.safe_float_order(order_val)
    
    @staticmethod
    def validate_order_number(order_number: Optional[float]) -> Tuple[bool, Optional[str]]:
        """
        Validate order number.
        
        Returns: (is_valid, error_message)
        """
        return SubmittalOrderingEngine.validate_order_number(order_number)
    
    @staticmethod
    def _submittal_to_dict(submittal) -> dict:
        """Convert submittal model object to plain dict."""
        return {
            'submittal_id': submittal.submittal_id,
            'order_number': submittal.order_number
        }
    
    @staticmethod
    def _submittals_to_dicts(submittals: List) -> List[dict]:
        """Convert list of submittal model objects to list of plain dicts."""
        return [SubmittalOrderingService._submittal_to_dict(s) for s in submittals]
    
    @staticmethod
    def categorize_submittals(submittals: List, exclude_id: str) -> Tuple[List, List]:
        """
        Categorize submittals into urgent (0 < order < 1) and regular (order >= 1).
        Excludes the submittal being updated and NULL values.
        
        Returns: (urgent_submittals, regular_submittals)
        """
        submittals_data = SubmittalOrderingService._submittals_to_dicts(submittals)
        urgent_data, regular_data = SubmittalOrderingEngine.categorize_submittals(submittals_data, exclude_id)
        
        # Map back to model objects
        submittal_map = {s.submittal_id: s for s in submittals}
        urgent = [submittal_map[s['submittal_id']] for s in urgent_data]
        regular = [submittal_map[s['submittal_id']] for s in regular_data]
        
        return urgent, regular

    @staticmethod
    def handle_set_to_null(submittal, all_group_submittals: List) -> List:
        """
        Handle setting order to NULL. Returns list of submittals that need updates.
        """
        submittal_data = SubmittalOrderingService._submittal_to_dict(submittal)
        all_group_submittals_data = SubmittalOrderingService._submittals_to_dicts(all_group_submittals)
        
        updates = SubmittalOrderingEngine.handle_set_to_null(submittal_data, all_group_submittals_data)
        
        # Map back to model objects
        submittal_map = {s.submittal_id: s for s in all_group_submittals}
        return [(submittal_map[submittal_id], new_order) for submittal_id, new_order in updates]

    @staticmethod
    def handle_set_to_urgent(submittal, new_order: float, all_group_submittals: List) -> List:
        """
        Handle setting order to urgent (0 < order < 1). Returns list of submittals that need updates.
        """
        submittal_data = SubmittalOrderingService._submittal_to_dict(submittal)
        all_group_submittals_data = SubmittalOrderingService._submittals_to_dicts(all_group_submittals)
        
        updates = SubmittalOrderingEngine.handle_set_to_urgent(submittal_data, new_order, all_group_submittals_data)
        
        # Map back to model objects
        submittal_map = {s.submittal_id: s for s in all_group_submittals}
        return [(submittal_map[submittal_id], new_order) for submittal_id, new_order in updates]

    @staticmethod
    def handle_set_to_regular(submittal, new_order: float, all_group_submittals: List) -> List:
        """
        Handle setting order to regular position (>= 1). Returns list of submittals that need updates.
        """
        submittal_data = SubmittalOrderingService._submittal_to_dict(submittal)
        all_group_submittals_data = SubmittalOrderingService._submittals_to_dicts(all_group_submittals)
        
        updates = SubmittalOrderingEngine.handle_set_to_regular(submittal_data, new_order, all_group_submittals_data)
        
        # Map back to model objects
        submittal_map = {s.submittal_id: s for s in all_group_submittals}
        return [(submittal_map[submittal_id], new_order) for submittal_id, new_order in updates]

    @staticmethod
    def calculate_updates(update_request: SubmittalOrderUpdate, all_group_submittals: List) -> List:
        """
        Calculate all submittal updates needed for the requested change.
        Returns: List of (submittal, new_order_value) tuples
        """
        all_group_submittals_data = SubmittalOrderingService._submittals_to_dicts(all_group_submittals)
        
        updates = SubmittalOrderingEngine.calculate_updates(update_request, all_group_submittals_data)
        
        # Map back to model objects
        submittal_map = {s.submittal_id: s for s in all_group_submittals}
        return [(submittal_map[submittal_id], new_order) for submittal_id, new_order in updates]


class UrgencyService:
    """Service for handling urgency-related business logic, including bumping and workflow checks."""
    
    @staticmethod
    def check_submitter_pending_in_workflow(approvers):
        """
        Check if the submitter (workflow_group_number 0) appears as a pending approver
        in the next workflow group that has pending approvers.
        
        Args:
            approvers: List of approver dictionaries from submittal data
            
        Returns:
            bool: True if submitter appears as pending in the next workflow group with pending approvers
        """
        result = UrgencyEngine.check_submitter_pending_in_workflow(approvers)
        if result:
            logger.info("Submitter found as pending in next workflow group")
        return result
    
    @staticmethod
    def bump_order_number_to_urgent(record, submittal_id, ball_in_court_value):
        """
        Convert an integer order number to an urgent decimal using the ladder system.
        Each drafter has urgency slots [0.1, 0.2, ..., 0.9]. When a submittal returns:
        - 0.1 = MOST urgent (oldest, been waiting longest)
        - 0.9 = LEAST urgent (newest, just arrived)
        - New urgent submittal gets 0.9 (least urgent position)
        - All existing urgent submittals shift DOWN by 0.1 (0.9 -> 0.8, 0.8 -> 0.7, etc.) toward 0.1
        - If all 9 slots are filled, the one at 0.1 (oldest) gets bumped to order 1 (regular status)
        - When bumping to regular, all regular orders (>= 1) shift UP by 1
        
        Args:
            record: ProcoreSubmittal DB record
            submittal_id: Submittal ID for logging
            ball_in_court_value: Current ball_in_court value for grouping
            
        Returns:
            bool: True if order number was bumped, False otherwise
        """
        logger.info(f"Starting ladder bump check for submittal {submittal_id}")
        
        if record.order_number is None:
            logger.warning(f"Order number is None for submittal {submittal_id}, cannot bump")
            return False
        
        current_order = record.order_number
        
        # Check if order_number is an integer >= 1
        is_integer = isinstance(current_order, (int, float)) and current_order >= 1 and current_order == int(current_order)
        
        if not is_integer:
            logger.warning(f"Order number {current_order} is not an integer >= 1 for submittal {submittal_id}, cannot bump")
            return False
        
        # Find all existing urgent submittals (0 < order < 1) for this ball_in_court
        existing_urgent_submittals = ProcoreSubmittal.query.filter(
            ProcoreSubmittal.ball_in_court == ball_in_court_value,
            ProcoreSubmittal.submittal_id != str(submittal_id),  # Exclude current submittal
            ProcoreSubmittal.order_number < 1,
            ProcoreSubmittal.order_number > 0,  # Must be > 0 (exclude NULL and 0)
            ProcoreSubmittal.order_number.isnot(None)
        ).all()
        
        # Find all regular submittals (order >= 1) for this ball_in_court
        existing_regular_submittals = ProcoreSubmittal.query.filter(
            ProcoreSubmittal.ball_in_court == ball_in_court_value,
            ProcoreSubmittal.submittal_id != str(submittal_id),  # Exclude current submittal
            ProcoreSubmittal.order_number >= 1,
            ProcoreSubmittal.order_number.isnot(None)
        ).all()
        
        # Convert to plain data structures
        urgent_data = [
            {'submittal_id': s.submittal_id, 'order_number': s.order_number}
            for s in existing_urgent_submittals
        ]
        regular_data = [
            {'submittal_id': s.submittal_id, 'order_number': s.order_number}
            for s in existing_regular_submittals
        ]
        
        # Call engine to calculate updates
        can_bump, new_order_for_bumped, urgent_updates, regular_updates = UrgencyEngine.calculate_bump_updates(
            current_order,
            urgent_data,
            regular_data
        )
        
        if not can_bump:
            return False
        
        # Apply urgent updates
        urgent_map = {s.submittal_id: s for s in existing_urgent_submittals}
        for submittal_id, new_order_val in urgent_updates:
            if submittal_id in urgent_map:
                # If it's an urgency slot (0 < order < 1), round to nearest tenth
                if new_order_val is not None and 0 < new_order_val < 1:
                    new_order_val = round(new_order_val, 1)
                urgent_map[submittal_id].order_number = new_order_val
                logger.info(f"Ladder shift DOWN: submittal {submittal_id} -> {new_order_val} (toward 0.1 = most urgent)")
        
        # Apply regular updates
        regular_map = {s.submittal_id: s for s in existing_regular_submittals}
        for submittal_id, new_order_val in regular_updates:
            if submittal_id in regular_map:
                regular_map[submittal_id].order_number = new_order_val
                logger.info(f"Regular shift UP: submittal {submittal_id} -> {new_order_val}")
        
        # Assign order number to the new submittal
        record.order_number = new_order_for_bumped
        
        if new_order_for_bumped == 1.0:
            logger.info(f"BUMPED: {int(current_order)} -> 1.0 for submittal {submittal_id} (all slots filled, assigned to regular)")
            logger.info(f"Shifted {len(regular_updates)} regular orders UP to make room")
        else:
            logger.info(f"BUMPED: {int(current_order)} -> {new_order_for_bumped} for submittal {submittal_id} (ladder system - newest at 0.9)")
            if urgent_updates:
                logger.info(f"Shifted {len(urgent_updates)} existing urgent submittals DOWN the ladder (toward 0.1 = most urgent)")
        
        return True
