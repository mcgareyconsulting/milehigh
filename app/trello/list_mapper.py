"""
Trello list mapping logic for syncing between database and Trello lists.

This module provides a mapper class that handles bidirectional mapping between
Excel/database status fields and Trello list names.
"""

from typing import Optional
from app.logging_config import get_logger

logger = get_logger(__name__)


class TrelloListMapper:
    """
    Mapper for converting between database status fields and Trello list names.
    
    This class handles:
    - Mapping database status to Trello list (for syncing Excel → Trello)
    - Mapping Trello list to database status (for syncing Trello → Excel)
    """
    
    # Valid shipping states that should be preserved during sync
    VALID_SHIPPING_STATES = [
        "Paint complete",
        "Store at MHMW for shipping",
        "Shipping planning"
    ]
    
    @classmethod
    def determine_trello_list_from_db(cls, rec) -> Optional[str]:
        """
        Determine the appropriate Trello list based on database record status.
        
        This is used to determine where a Trello card should be placed
        based on database record status.
        
        Args:
            rec: Database record (Job model instance) with cut_start, fitup_comp, welded,
                 paint_comp, and ship fields
                 
        Returns:
            Trello list name, or None if no matching list is found
            
        Mapping logic:
        - If cut_start=X and other fields are empty → "Cut start"
        - If fitup_comp=X, welded=X, paint_comp=X, ship=ST → "Store at MHMW for shipping"
        - If fitup_comp=X, welded=X, paint_comp=X, ship=RS → "Shipping planning"
        - If fitup_comp=X, welded=X, paint_comp=X, ship=O/T/""/None → "Paint complete"
        - If fitup_comp=X, welded=O, paint_comp="", ship=T/O/"" → "Fit Up Complete."
        - If fitup_comp=X, welded=X, paint_comp=X, ship=X → "Shipping completed"
        - Otherwise → None
        """
        # Check for "Cut start" stage
        if (
            rec.cut_start == "X"
            and (not rec.fitup_comp or rec.fitup_comp == "")
            and (not rec.welded or rec.welded == "")
            and (not rec.paint_comp or rec.paint_comp == "")
            and (not rec.ship or rec.ship == "")
        ):
            return "Cut start"
        if (
            rec.fitup_comp == "X"
            and rec.welded == "X"
            and rec.paint_comp == "X"
            and rec.ship == "ST"
        ):
            return "Store at MHMW for shipping"
        if (
            rec.fitup_comp == "X"
            and rec.welded == "X"
            and rec.paint_comp == "X"
            and rec.ship == "RS"
        ):
            return "Shipping planning"
        if (
            rec.fitup_comp == "X"
            and rec.welded == "X"
            and rec.paint_comp == "X"
            and (rec.ship == "O" or rec.ship == "T" or rec.ship == None or rec.ship == "")
        ):
            return "Paint complete"
        elif (
            rec.fitup_comp == "X"
            and rec.welded == "O"
            and (rec.paint_comp == "" or rec.paint_comp == None)
            and (rec.ship == "T" or rec.ship == "O" or rec.ship == "" or rec.ship == None)
        ):
            return "Fit Up Complete."
        elif (
            rec.fitup_comp == "X"
            and rec.welded == "X"
            and rec.paint_comp == "X"
            and (rec.ship == "X")
        ):
            return "Shipping completed"
        else:
            return None  # no matching list
    
    @classmethod
    def apply_trello_list_to_db(cls, job, trello_list_name: str, operation_id: str) -> None:
        """
        Update database record stage based on Trello list movement.
        
        This is used when syncing from Trello to database to update
        the stage field based on which list the card was moved to.
        
        Args:
            job: Database record (Job model instance) to update
            trello_list_name: Name of the Trello list the card was moved to
            operation_id: Sync operation ID for logging
            
        Returns:
            None (modifies job in place)
        """
        # Log the current state before applying changes
        old_stage = job.stage
        logger.info(
            "Applying Trello list to database record",
            operation_id=operation_id,
            job_id=job.id,
            trello_list=trello_list_name,
            current_stage=old_stage
        )
        
        # Set the stage directly from the Trello list name
        job.stage = trello_list_name
        
        # Log the new state after applying changes
        logger.info(
            "Applied Trello list to database record",
            operation_id=operation_id,
            job_id=job.id,
            new_stage=job.stage
        )
    
    @classmethod
    def is_valid_shipping_state(cls, list_name: str) -> bool:
        """
        Check if a list name is a valid shipping state that should be preserved.
        
        Args:
            list_name: Name of the Trello list
            
        Returns:
            True if the list is a valid shipping state
        """
        return list_name in cls.VALID_SHIPPING_STATES

