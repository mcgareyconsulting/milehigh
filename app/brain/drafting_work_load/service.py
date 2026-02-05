# dwl_ordering.py
"""
Service layer for Drafting Work Load operations.
Consolidates all DWL business logic for easier testing and maintenance.
"""
from datetime import datetime
from typing import Optional, List, Tuple
from dataclasses import dataclass
import logging
from app.models import db, ProcoreSubmittal

logger = logging.getLogger(__name__)


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
        """
        validated_notes = DraftingWorkLoadService.validate_notes(notes)
        submittal.notes = validated_notes
        submittal.last_updated = datetime.utcnow()
    
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
        
        Stack/FIFO behavior: Position determines urgency, slots compress to fill from bottom (0.1, 0.2, 0.3...)
        After assignment, all urgency slots are compressed to fill gaps.
        """
        old_order = SubmittalOrderingService.safe_float_order(submittal.order_number)
        updates = []
        
        # Round urgency slot to nearest tenth place to ensure exact values (0.1, 0.2, ..., 0.9)
        rounded_order = round(new_order, 1)
        
        # If old value was >= 1, renumber those greater than old value
        if old_order is not None and old_order >= 1:
            for s in all_group_submittals:
                if s.submittal_id == submittal.submittal_id:
                    continue
                
                s_order = SubmittalOrderingService.safe_float_order(s.order_number)
                if s_order is not None and s_order >= 1 and s_order > old_order:
                    updates.append((s, s_order - 1))
        
        # Update the target submittal to new urgent value (rounded to tenth place)
        updates.append((submittal, rounded_order))
        
        # Compress all urgency slots: sort by order (oldest/most urgent first) and reassign from 0.9 downward
        # Oldest (most urgent) gets lowest slot, newest (least urgent) gets 0.9
        # Example: 3 items → [0.7, 0.8, 0.9] where oldest is at 0.7, newest at 0.9
        urgent_submittals = []
        for s in all_group_submittals:
            # Use the new order if this is the submittal being updated, otherwise use current order
            if s.submittal_id == submittal.submittal_id:
                s_order = rounded_order
            else:
                s_order = SubmittalOrderingService.safe_float_order(s.order_number)
            
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
                    for i, (update_s, update_order) in enumerate(updates):
                        if update_s.submittal_id == s.submittal_id:
                            already_updated = True
                            update_index = i
                            break
                    
                    if not already_updated:
                        updates.append((s, new_slot))
                    else:
                        # Update the existing update entry
                        updates[update_index] = (s, new_slot)
        
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


class UrgencyService:
    """Service for handling urgency-related business logic, including bumping and workflow checks."""
    
    @staticmethod
    def check_submitter_pending_in_workflow(approvers):
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
        print(f"[SUBMITTER CHECK] Starting check with {len(approvers) if approvers else 0} approvers")
        logger.info(f"[SUBMITTER CHECK] Starting check with {len(approvers) if approvers else 0} approvers")
        
        if not approvers or not isinstance(approvers, list):
            print(f"[SUBMITTER CHECK] No approvers list or invalid type")
            logger.info(f"[SUBMITTER CHECK] No approvers list or invalid type")
            return False
        
        # Find the submitter (workflow_group_number 0)
        submitter = None
        print(f"[SUBMITTER CHECK] Searching for submitter (workflow_group_number 0)...")
        logger.info(f"[SUBMITTER CHECK] Searching for submitter (workflow_group_number 0)...")
        
        for approver in approvers:
            if not isinstance(approver, dict):
                continue
            workflow_group = approver.get("workflow_group_number")
            print(f"[SUBMITTER CHECK] Checking approver with workflow_group_number={workflow_group}")
            logger.info(f"[SUBMITTER CHECK] Checking approver with workflow_group_number={workflow_group}")
            
            if workflow_group == 0:
                user = approver.get("user")
                if user and isinstance(user, dict):
                    submitter = {
                        "name": user.get("name"),
                        "login": user.get("login")
                    }
                    print(f"[SUBMITTER CHECK] Found submitter: name='{submitter.get('name')}', login='{submitter.get('login')}'")
                    logger.info(f"[SUBMITTER CHECK] Found submitter: name='{submitter.get('name')}', login='{submitter.get('login')}'")
                break
        
        if not submitter:
            print(f"[SUBMITTER CHECK] No submitter found (workflow_group_number 0 not found)")
            logger.info(f"[SUBMITTER CHECK] No submitter found (workflow_group_number 0 not found)")
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
                    print(f"[SUBMITTER CHECK] Found pending approver in workflow_group_number={workflow_group}")
                    logger.info(f"[SUBMITTER CHECK] Found pending approver in workflow_group_number={workflow_group}")
        
        if not pending_workflow_groups:
            print(f"[SUBMITTER CHECK] No pending workflow groups found")
            logger.info(f"[SUBMITTER CHECK] No pending workflow groups found")
            return False
        
        # Find the minimum workflow group number (the next one in line)
        next_workflow_group = min(pending_workflow_groups)
        print(f"[SUBMITTER CHECK] Next pending workflow group to check: {next_workflow_group}")
        logger.info(f"[SUBMITTER CHECK] Next pending workflow group to check: {next_workflow_group}")
        
        # Check if submitter appears as pending in the NEXT workflow group only
        print(f"[SUBMITTER CHECK] Checking if submitter appears as pending in workflow_group_number={next_workflow_group}...")
        logger.info(f"[SUBMITTER CHECK] Checking if submitter appears as pending in workflow_group_number={next_workflow_group}...")
        
        for approver in approvers:
            if not isinstance(approver, dict):
                continue
            
            workflow_group = approver.get("workflow_group_number")
            # Only check approvers in the next workflow group
            if workflow_group != next_workflow_group:
                continue
            
            print(f"[SUBMITTER CHECK] Checking approver at workflow_group_number={workflow_group}")
            logger.info(f"[SUBMITTER CHECK] Checking approver at workflow_group_number={workflow_group}")
            
            # Check if response is "Pending"
            response = approver.get("response", {})
            if not isinstance(response, dict):
                print(f"[SUBMITTER CHECK]   Response is not a dict, skipping")
                logger.info(f"[SUBMITTER CHECK]   Response is not a dict, skipping")
                continue
            
            response_name = response.get("name", "").strip()
            print(f"[SUBMITTER CHECK]   Response name: '{response_name}'")
            logger.info(f"[SUBMITTER CHECK]   Response name: '{response_name}'")
            
            if response_name.lower() != "pending":
                print(f"[SUBMITTER CHECK]   Response is not 'Pending', skipping")
                logger.info(f"[SUBMITTER CHECK]   Response is not 'Pending', skipping")
                continue
            
            # Check if user matches submitter
            user = approver.get("user")
            if not user or not isinstance(user, dict):
                print(f"[SUBMITTER CHECK]   User is not a dict, skipping")
                logger.info(f"[SUBMITTER CHECK]   User is not a dict, skipping")
                continue
            
            approver_name = user.get("name")
            approver_login = user.get("login")
            print(f"[SUBMITTER CHECK]   Approver user: name='{approver_name}', login='{approver_login}'")
            logger.info(f"[SUBMITTER CHECK]   Approver user: name='{approver_name}', login='{approver_login}'")
            
            # Match by name or login
            name_match = (submitter.get("name") and approver_name and 
                         submitter.get("name").lower() == approver_name.lower())
            login_match = (submitter.get("login") and approver_login and 
                          submitter.get("login").lower() == approver_login.lower())
            
            print(f"[SUBMITTER CHECK]   Name match: {name_match}, Login match: {login_match}")
            logger.info(f"[SUBMITTER CHECK]   Name match: {name_match}, Login match: {login_match}")
            
            if name_match or login_match:
                print(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('name')}' appears as pending at workflow_group_number={workflow_group}")
                logger.info(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('name')}' appears as pending at workflow_group_number={workflow_group}")
                return True
        
        # No match found in the next workflow group
        print(f"[SUBMITTER CHECK] ✗ No match found: Submitter does not appear as pending in workflow_group_number={next_workflow_group}")
        logger.info(f"[SUBMITTER CHECK] ✗ No match found: Submitter does not appear as pending in workflow_group_number={next_workflow_group}")
        return False
    
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
        - When bumping to regular, all regular orders (>= 1) shift DOWN by 1
        
        Args:
            record: ProcoreSubmittal DB record
            submittal_id: Submittal ID for logging
            ball_in_court_value: Current ball_in_court value for grouping
            
        Returns:
            bool: True if order number was bumped, False otherwise
        """
        print(f"[ORDER BUMP] Starting ladder bump check for submittal {submittal_id}")
        logger.info(f"[ORDER BUMP] Starting ladder bump check for submittal {submittal_id}")
        
        if record.order_number is None:
            print(f"[ORDER BUMP] Order number is None, cannot bump")
            logger.info(f"[ORDER BUMP] Order number is None, cannot bump")
            return False
        
        current_order = record.order_number
        print(f"[ORDER BUMP] Current order number: {current_order} (type: {type(current_order)})")
        logger.info(f"[ORDER BUMP] Current order number: {current_order} (type: {type(current_order)})")
        
        # Check if order_number is an integer >= 1
        is_integer = isinstance(current_order, (int, float)) and current_order >= 1 and current_order == int(current_order)
        print(f"[ORDER BUMP] Is integer >= 1: {is_integer}")
        logger.info(f"[ORDER BUMP] Is integer >= 1: {is_integer}")
        
        if not is_integer:
            print(f"[ORDER BUMP] Order number is not an integer >= 1, cannot bump")
            logger.info(f"[ORDER BUMP] Order number is not an integer >= 1, cannot bump")
            return False
        
        # Find all existing urgent submittals (0 < order < 1) for this ball_in_court
        print(f"[ORDER BUMP] Checking for existing urgent orders with ball_in_court='{ball_in_court_value}'")
        logger.info(f"[ORDER BUMP] Checking for existing urgent orders with ball_in_court='{ball_in_court_value}'")
        
        existing_urgent_submittals = ProcoreSubmittal.query.filter(
            ProcoreSubmittal.ball_in_court == ball_in_court_value,
            ProcoreSubmittal.submittal_id != str(submittal_id),  # Exclude current submittal
            ProcoreSubmittal.order_number < 1,
            ProcoreSubmittal.order_number > 0,  # Must be > 0 (exclude NULL and 0)
            ProcoreSubmittal.order_number.isnot(None)
        ).all()
        
        existing_urgent_orders = [float(s.order_number) for s in existing_urgent_submittals if s.order_number is not None]
        
        print(f"[ORDER BUMP] Found {len(existing_urgent_submittals)} existing urgent submittals with orders: {existing_urgent_orders}")
        logger.info(f"[ORDER BUMP] Found {len(existing_urgent_submittals)} existing urgent submittals with orders: {existing_urgent_orders}")
        
        # Check if 0.9 is already occupied
        slot_09_occupied = 0.9 in existing_urgent_orders
        
        # Check if all 9 slots are filled (0.1 through 0.9)
        has_all_slots_filled = len(existing_urgent_submittals) >= 9
        
        # Ladder system: only shift existing urgent orders if 0.9 is occupied
        # Valid urgency slots are [0.1, 0.2, ..., 0.9] where 0.1 = most urgent (oldest), 0.9 = least urgent (newest)
        # If 0.9 is NOT occupied, just assign 0.9 to new submittal without shifting others
        # If 0.9 IS occupied but not all slots filled, shift all existing urgent orders DOWN by 0.1 (toward 0.1 = most urgent)
        # If all 9 slots are filled, assign order 1 to new submittal and shift all regular orders up by 1
        updates = []
        needs_regular_shift = False
        regular_submittals_count = 0
        
        if has_all_slots_filled:
            # All 9 slots are filled - new urgent gets order 1, regular orders shift up
            needs_regular_shift = True
            print(f"[ORDER BUMP] All 9 urgency slots filled, assigning order 1 to new urgent submittal and shifting regular orders up")
            logger.info(f"[ORDER BUMP] All 9 urgency slots filled, assigning order 1 to new urgent submittal and shifting regular orders up")
        elif not slot_09_occupied:
            # 0.9 is available - just assign it to new submittal, no need to shift existing ones
            print(f"[ORDER BUMP] Slot 0.9 is available, assigning to new submittal without shifting existing urgent submittals")
            logger.info(f"[ORDER BUMP] Slot 0.9 is available, assigning to new submittal without shifting existing urgent submittals")
        else:
            # 0.9 is occupied but not all slots filled - need to shift existing urgent submittals down to make room
            # Find available slots and only shift items that need to move to fill gaps
            all_slots = set([round(i * 0.1, 1) for i in range(1, 10)])  # {0.1, 0.2, ..., 0.9}
            occupied_slots = set(existing_urgent_orders)
            available_slots = sorted(all_slots - occupied_slots, reverse=True)  # Sort descending
            
            if available_slots:
                # Find the highest available slot below 0.9
                # We need to shift items starting from 0.9 downward until we hit an available slot
                highest_available_below_09 = max([s for s in available_slots if s < 0.9], default=None)
                
                if highest_available_below_09 is not None:
                    # Only shift items at positions > highest_available_below_09
                    # These are the items that need to move down to fill the gap
                    # Sort existing urgent submittals by order (descending) to process from highest to lowest
                    sorted_urgent = sorted(existing_urgent_submittals, key=lambda s: float(s.order_number), reverse=True)
                    
                    for submittal in sorted_urgent:
                        old_order = float(submittal.order_number)
                        # Only shift items that are above the highest available slot
                        # For example, if 0.8 is available, only shift items at 0.9
                        if old_order > highest_available_below_09:
                            # This item needs to shift down to make room
                            new_order = old_order - 0.1  # Shift DOWN toward 0.1 (most urgent)
                            
                            if new_order < 0.1:
                                # This shouldn't happen if we're managing slots correctly, but handle edge case
                                print(f"[ORDER BUMP] Warning: new_order {new_order} < 0.1, capping at 0.1")
                                logger.warning(f"[ORDER BUMP] Warning: new_order {new_order} < 0.1, capping at 0.1")
                                new_order = 0.1
                            else:
                                # Round to nearest tenth place to ensure exact values (0.1, 0.2, ..., 0.9)
                                new_order = round(new_order, 1)
                            updates.append((submittal, new_order))
                            print(f"[ORDER BUMP] Ladder shift DOWN: submittal {submittal.submittal_id} {old_order} -> {new_order} (toward 0.1 = most urgent)")
                            logger.info(f"[ORDER BUMP] Ladder shift DOWN: submittal {submittal.submittal_id} {old_order} -> {new_order} (toward 0.1 = most urgent)")
                else:
                    # No available slots below 0.9 - this shouldn't happen if not all slots are filled
                    # Fall back to shifting all items
                    sorted_urgent = sorted(existing_urgent_submittals, key=lambda s: float(s.order_number))
                    for submittal in sorted_urgent:
                        old_order = float(submittal.order_number)
                        new_order = old_order - 0.1
                        if new_order < 0.1:
                            new_order = 0.1
                        else:
                            # Round to nearest tenth place to ensure exact values (0.1, 0.2, ..., 0.9)
                            new_order = round(new_order, 1)
                        updates.append((submittal, new_order))
                        print(f"[ORDER BUMP] Ladder shift DOWN: submittal {submittal.submittal_id} {old_order} -> {new_order} (toward 0.1 = most urgent)")
                        logger.info(f"[ORDER BUMP] Ladder shift DOWN: submittal {submittal.submittal_id} {old_order} -> {new_order} (toward 0.1 = most urgent)")
            else:
                # No available slots - this shouldn't happen if not all slots are filled, but handle edge case
                sorted_urgent = sorted(existing_urgent_submittals, key=lambda s: float(s.order_number))
                for submittal in sorted_urgent:
                    old_order = float(submittal.order_number)
                    new_order = old_order - 0.1
                    if new_order < 0.1:
                        new_order = 0.1
                    else:
                        # Round to nearest tenth place to ensure exact values (0.1, 0.2, ..., 0.9)
                        new_order = round(new_order, 1)
                    updates.append((submittal, new_order))
                    print(f"[ORDER BUMP] Ladder shift DOWN: submittal {submittal.submittal_id} {old_order} -> {new_order} (toward 0.1 = most urgent)")
                    logger.info(f"[ORDER BUMP] Ladder shift DOWN: submittal {submittal.submittal_id} {old_order} -> {new_order} (toward 0.1 = most urgent)")
        
        # If all slots are filled, we need to shift all regular orders (>= 1) UP by 1
        if needs_regular_shift:
            # Find all regular submittals (order >= 1) for this ball_in_court
            regular_submittals = ProcoreSubmittal.query.filter(
                ProcoreSubmittal.ball_in_court == ball_in_court_value,
                ProcoreSubmittal.submittal_id != str(submittal_id),  # Exclude current submittal
                ProcoreSubmittal.order_number >= 1,
                ProcoreSubmittal.order_number.isnot(None)
            ).all()
            
            regular_submittals_count = len(regular_submittals)
            
            # Sort by order number (descending) so we shift from highest to lowest to avoid collisions
            regular_submittals.sort(key=lambda s: float(s.order_number) if s.order_number is not None else 0, reverse=True)
            
            # Shift all regular orders UP by 1 (1 -> 2, 2 -> 3, etc.)
            for submittal in regular_submittals:
                old_order = float(submittal.order_number)
                new_order = old_order + 1  # Shift UP means higher numbers (less urgent)
                updates.append((submittal, new_order))
                print(f"[ORDER BUMP] Regular shift UP: submittal {submittal.submittal_id} {old_order} -> {new_order}")
                logger.info(f"[ORDER BUMP] Regular shift UP: submittal {submittal.submittal_id} {old_order} -> {new_order}")
        
        # Apply all updates, rounding urgency slots to tenth place
        for submittal, new_order_val in updates:
            # If it's an urgency slot (0 < order < 1), round to nearest tenth
            if new_order_val is not None and 0 < new_order_val < 1:
                new_order_val = round(new_order_val, 1)
            submittal.order_number = new_order_val
        
        # Assign order number to the new submittal
        if needs_regular_shift:
            # All slots filled - assign order 1 (regular status)
            record.order_number = 1.0
            print(f"[ORDER BUMP] ✓ BUMPED: {int(current_order)} -> 1.0 for submittal {submittal_id} (all slots filled, assigned to regular)")
            logger.info(f"[ORDER BUMP] ✓ BUMPED: {int(current_order)} -> 1.0 for submittal {submittal_id} (all slots filled, assigned to regular)")
            print(f"[ORDER BUMP] Shifted {regular_submittals_count} regular orders UP to make room")
            logger.info(f"[ORDER BUMP] Shifted {regular_submittals_count} regular orders UP to make room")
        else:
            # Assign 0.9 to the new submittal (least urgent, newest position)
            record.order_number = 0.9
            print(f"[ORDER BUMP] ✓ BUMPED: {int(current_order)} -> 0.9 for submittal {submittal_id} (ladder system - newest at 0.9)")
            logger.info(f"[ORDER BUMP] ✓ BUMPED: {int(current_order)} -> 0.9 for submittal {submittal_id} (ladder system - newest at 0.9)")
            if updates:
                urgent_updates_count = len([u for u in updates if u[1] < 1])
                print(f"[ORDER BUMP] Shifted {urgent_updates_count} existing urgent submittals DOWN the ladder (toward 0.1 = most urgent)")
                logger.info(f"[ORDER BUMP] Shifted {urgent_updates_count} existing urgent submittals DOWN the ladder (toward 0.1 = most urgent)")
        
        return True

