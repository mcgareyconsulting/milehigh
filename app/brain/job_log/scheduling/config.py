"""
Scheduling configuration module.

This module defines all scheduling parameters that must match Excel behavior.
All values are frozen until real stage-duration data is collected.
"""

from typing import Dict


class SchedulingConfig:
    """
    Configuration for scheduling calculations.
    
    All values are fixed to match Excel behavior exactly.
    DO NOT CHANGE these values without explicit approval.
    """
    
    # Stage → Remaining Fab % Mapping
    # This is the authoritative mapping that replaces all legacy Excel logic
    # Maps both canonical names and database variations
    STAGE_REMAINING_FAB_PERCENTAGE: Dict[str, float] = {
        # Released - 100%
        'Released': 1.0,
        
        # Cut Start - 90% (handles variations)
        'Cut Start': 0.9,
        'Cut start': 0.9,
        
        # Fit Up Complete - 50% (handles variations)
        'Fit up Comp': 0.5,
        'Fit Up Complete.': 0.5,
        'Fit Up Complete': 0.5,
        'Fitup comp': 0.5,
        
        # Welding/Welded QC - 10% (handles variations)
        'WeldingQC': 0.1,
        'Welded QC': 0.1,
        'Welding QC': 0.1,
        
        # Paint Complete - 0% (handles variations)
        'Paint Complete': 0.0,
        'Paint complete': 0.0,
        'Paint comp': 0.0,
        
        # Store - 0%
        'Store': 0.0,
        'Store at MHMW for shipping': 0.0,
        
        # Ship Planning - 0%
        'Ship Planning': 0.0,
        'Shipping planning': 0.0,
        
        # Ship Complete - 0% (handles variations)
        'Ship Complete': 0.0,
        'Shipping completed': 0.0,
        
        # Complete - 0%
        'Complete': 0.0,
    }
    
    # Fabrication capacity (fixed daily capacity)
    FAB_HOURS_PER_DAY: float = 8.0  # Adjust if Excel uses different value
    
    # Installation capacity (fixed daily capacity)
    INSTALL_HOURS_PER_DAY: float = 16.0
    
    # Install buffer (working days between fab completion and install start)
    INSTALL_BUFFER_DAYS: int = 3
    
    @classmethod
    def get_stage_remaining_percentage(cls, stage: str) -> float:
        """
        Get the remaining fabrication percentage for a given stage.
        
        Args:
            stage: Stage name (e.g., 'Released', 'Cut Start', 'Fit Up Complete.', etc.)
            
        Returns:
            float: Percentage as decimal (0.0 to 1.0)
            
        Note:
            Returns 1.0 (100%) for unknown stages to be conservative.
        """
        if not stage:
            return 1.0  # Default to 100% for empty/None stages
        
        # Normalize stage name (strip whitespace)
        normalized_stage = stage.strip()
        
        # Try exact match first
        if normalized_stage in cls.STAGE_REMAINING_FAB_PERCENTAGE:
            return cls.STAGE_REMAINING_FAB_PERCENTAGE[normalized_stage]
        
        # Try case-insensitive match
        normalized_lower = normalized_stage.lower()
        for key, value in cls.STAGE_REMAINING_FAB_PERCENTAGE.items():
            if key.lower() == normalized_lower:
                return value
        
        # Default to 100% for unknown stages (conservative)
        return 1.0

