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
    - Mapping database stage to Trello list (many-to-one: ~20 DB stages → 6 Trello lists)
    - Mapping Trello list to database stage (for syncing Trello → DB)
    - Validating inbound Trello list names before applying to DB
    """

    # Valid shipping states that should be preserved during sync
    VALID_SHIPPING_STATES = [
        "Paint complete",
        "Store at MHMW for shipping",
        "Shipping planning"
    ]

    # The 6 actual Trello lists on the board
    VALID_TRELLO_LISTS = {
        "Released",
        "Fit Up Complete.",
        "Paint complete",
        "Store at MHMW for shipping",
        "Shipping planning",
        "Shipping completed",
    }

    # Many-to-one mapping: every DB stage maps to exactly one Trello list.
    # Stages before Fitup Start stay on "Released".
    # Stages from Fitup Start through Welded QC (and Hold) map to "Fit Up Complete.".
    # Later stages map 1:1 to their Trello list name.
    DB_STAGE_TO_TRELLO_LIST = {
        # Released group — card stays on Released
        "Released":                     "Released",
        "Cut start":                    "Released",
        "Cut Start":                    "Released",
        "Cut Complete":                 "Released",
        "Material Ordered":             "Released",
        # Fit Up Complete. group — card moves to Fit Up Complete.
        "Fitup Start":                  "Fit Up Complete.",
        "Fitup Complete":               "Fit Up Complete.",
        "Fit Up Complete.":             "Fit Up Complete.",
        "Weld Start":                   "Fit Up Complete.",
        "Weld Complete":                "Fit Up Complete.",
        "Welded":                       "Fit Up Complete.",
        "Welded QC":                    "Fit Up Complete.",
        "Hold":                         "Fit Up Complete.",
        "Paint Start":                  "Fit Up Complete.",
        # 1:1 stages
        "Paint complete":               "Paint complete",
        "Paint Complete":               "Paint complete",
        "Store at MHMW for shipping":   "Store at MHMW for shipping",
        "Store at Shop":                "Store at MHMW for shipping",
        "Shipping planning":            "Shipping planning",
        "Shipping Planning":            "Shipping planning",
        "Shipping completed":           "Shipping completed",
        "Shipping Complete":            "Shipping completed",
        "Complete":                     "Shipping completed",
    }
    
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
    def get_trello_list_for_stage(cls, stage: Optional[str]) -> Optional[str]:
        """
        Map a database stage to the expected Trello list name.

        Uses DB_STAGE_TO_TRELLO_LIST for an exact match first, then falls back
        to a case-insensitive lookup.

        Args:
            stage: Database stage value

        Returns:
            Trello list name, or None if the stage is not recognized
        """
        if not stage:
            return None

        # Exact match
        trello_list = cls.DB_STAGE_TO_TRELLO_LIST.get(stage)
        if trello_list is not None:
            return trello_list

        # Case-insensitive fallback
        stage_lower = stage.lower()
        for key, value in cls.DB_STAGE_TO_TRELLO_LIST.items():
            if key.lower() == stage_lower:
                return value

        logger.warning("No Trello list mapping for stage", stage=stage)
        return None

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
        # Validate that the Trello list name is one we recognise
        if trello_list_name not in cls.VALID_TRELLO_LISTS:
            logger.warning(
                "Ignoring unknown Trello list name — stage will not be updated",
                operation_id=operation_id,
                job_id=job.id,
                trello_list=trello_list_name,
                current_stage=job.stage,
            )
            return

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
        
        # Update stage_group based on stage
        from app.api.helpers import get_stage_group_from_stage
        job.stage_group = get_stage_group_from_stage(trello_list_name)
        
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

