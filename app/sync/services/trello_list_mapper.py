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
        
        This is used when syncing from OneDrive/Excel to Trello to determine
        where a card should be placed.
        
        Args:
            rec: Database record (Job model instance) with fitup_comp, welded,
                 paint_comp, and ship fields
                 
        Returns:
            Trello list name, or None if no matching list is found
            
        Mapping logic:
        - If fitup_comp=X, welded=X, paint_comp=X, ship=O or T → "Paint complete"
        - If fitup_comp=X, welded=O, paint_comp="", ship=T/O/"" → "Fit Up Complete."
        - If fitup_comp=X, welded=X, paint_comp=X, ship=X → "Shipping completed"
        - Otherwise → None
        """
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
        Update database record status based on Trello list movement.
        
        This is used when syncing from Trello to Excel/database to update
        the status fields based on which list the card was moved to.
        
        Args:
            job: Database record (Job model instance) to update
            trello_list_name: Name of the Trello list the card was moved to
            operation_id: Sync operation ID for logging
            
        Returns:
            None (modifies job in place)
            
        Mapping logic:
        - "Paint complete" → fitup_comp=X, welded=X, paint_comp=X, ship=O
        - "Store at MHMW for shipping" → fitup_comp=X, welded=X, paint_comp=X, ship=O
        - "Shipping planning" → fitup_comp=X, welded=X, paint_comp=X, ship=""
        - "Fit Up Complete." → fitup_comp=X, welded=O, paint_comp="", ship=""
        - "Shipping completed" → fitup_comp=X, welded=X, paint_comp=X, ship=X
        - "Released" → fitup_comp="", welded="", paint_comp="", ship=""
        """
        # Log the current state before applying changes
        logger.info(
            "Applying Trello list to database record",
            operation_id=operation_id,
            job_id=job.id,
            trello_list=trello_list_name,
            current_status={
                "fitup_comp": job.fitup_comp,
                "welded": job.welded,
                "paint_comp": job.paint_comp,
                "ship": job.ship
            }
        )
        
        # Apply the mapping based on Trello list name
        if trello_list_name == "Paint complete":
            job.fitup_comp = "X"
            job.welded = "X"
            job.paint_comp = "X"
            job.ship = "O"
        elif trello_list_name == "Store at MHMW for shipping":
            job.fitup_comp = "X"
            job.welded = "X"
            job.paint_comp = "X"
            job.ship = "O"
        elif trello_list_name == "Shipping planning":
            job.fitup_comp = "X"
            job.welded = "X"
            job.paint_comp = "X"
            job.ship = ""
        elif trello_list_name == "Fit Up Complete.":
            job.fitup_comp = "X"
            job.welded = "O"
            job.paint_comp = ""
            job.ship = ""
        elif trello_list_name == "Shipping completed":
            job.fitup_comp = "X"
            job.welded = "X"
            job.paint_comp = "X"
            job.ship = "X"
        elif trello_list_name == "Released":
            job.fitup_comp = ""
            job.welded = ""
            job.paint_comp = ""
            job.ship = ""
        
        # Log the new state after applying changes
        logger.info(
            "Applied Trello list to database record",
            operation_id=operation_id,
            job_id=job.id,
            new_status={
                "fitup_comp": job.fitup_comp,
                "welded": job.welded,
                "paint_comp": job.paint_comp,
                "ship": job.ship
            }
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

