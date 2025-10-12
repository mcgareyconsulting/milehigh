"""
Configuration classes for sync operations to replace hardcoded mappings and reduce conditional complexity.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Any
from enum import Enum


class SyncSource(Enum):
    """Source systems for sync operations."""
    TRELLO = "trello"
    ONEDRIVE = "onedrive"
    SYSTEM = "system"


class SyncEventType(Enum):
    """Types of sync events."""
    CARD_CREATED = "card_created"
    CARD_UPDATED = "card_updated"
    CARD_MOVED = "card_moved"
    EXCEL_UPDATED = "excel_updated"
    UNHANDLED = "unhandled"


@dataclass
class TrelloListMapping:
    """Configuration for Trello list mappings and their corresponding database field states."""
    list_name: str
    fitup_comp: str
    welded: str
    paint_comp: str
    ship: str


@dataclass
class ExcelFieldMapping:
    """Configuration for Excel field to database field mappings."""
    excel_column: str
    db_field: str
    field_type: str  # 'text', 'date', 'number'


@dataclass
class SyncConfig:
    """Main configuration class for sync operations."""
    
    # Trello list mappings
    trello_list_mappings: Dict[str, TrelloListMapping] = None
    
    # Excel field mappings
    excel_field_mappings: list[ExcelFieldMapping] = None
    
    # Excel columns for updates
    excel_update_columns: Dict[str, str] = None  # column -> cell mapping
    
    def __post_init__(self):
        if self.trello_list_mappings is None:
            self.trello_list_mappings = {
                "Paint complete": TrelloListMapping(
                    list_name="Paint complete",
                    fitup_comp="X",
                    welded="X", 
                    paint_comp="X",
                    ship="T"
                ),
                "Fit Up Complete.": TrelloListMapping(
                    list_name="Fit Up Complete.",
                    fitup_comp="X",
                    welded="O",
                    paint_comp="",
                    ship="T"
                ),
                "Shipping completed": TrelloListMapping(
                    list_name="Shipping completed",
                    fitup_comp="X",
                    welded="X",
                    paint_comp="X",
                    ship="X"
                )
            }
        
        if self.excel_field_mappings is None:
            self.excel_field_mappings = [
                ExcelFieldMapping("Fitup comp", "fitup_comp", "text"),
                ExcelFieldMapping("Welded", "welded", "text"),
                ExcelFieldMapping("Paint Comp", "paint_comp", "text"),
                ExcelFieldMapping("Ship", "ship", "text"),
                ExcelFieldMapping("Start install", "start_install", "date"),
            ]
        
        if self.excel_update_columns is None:
            self.excel_update_columns = {
                "fitup_comp": "M",
                "welded": "N", 
                "paint_comp": "O",
                "ship": "P",
            }


# Global configuration instance
sync_config = SyncConfig()
