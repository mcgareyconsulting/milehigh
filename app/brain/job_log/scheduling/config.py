"""
@milehigh-header
schema_version: 1
purpose: Define frozen scheduling constants (capacity, buffer, stage percentages) that must match the legacy Excel workbook exactly.
exports:
  SchedulingConfig: Class with FAB_HOURS_PER_DAY, INSTALL_HOURS_PER_DAY, INSTALL_BUFFER_DAYS, stage-remaining map, and lookup method
imports_from: [typing]
imported_by: [app/brain/job_log/scheduling/__init__.py, app/brain/job_log/scheduling/calculator.py]
invariants:
  - DO NOT change numeric values without explicit approval -- they mirror the Excel workbook
  - get_stage_remaining_percentage returns 1.0 (100%) for unknown stages
  - Stage lookup is case-insensitive as a fallback
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

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
    
    # Stage → Remaining Fab % Mapping (canonical names only).
    # Values mirror the Excel workbook; do not change without explicit approval.
    # Note: app.api.helpers.STAGE_HOUR_PERCENTAGES is the future source of truth
    # for both fab and install percentages (per the client "Banana Code" matrix);
    # this dict is the legacy fab-only map still consumed by the scheduling
    # calculator. Values here have not been reconciled with the new matrix yet.
    STAGE_REMAINING_FAB_PERCENTAGE: Dict[str, float] = {
        'Released':         1.0,
        'Material Ordered': 1.0,
        'Cut Start':        0.9,
        'Cut Complete':     0.9,
        'Fitup Start':      0.9,
        'Fitup Complete':   0.5,
        'Weld Start':       0.5,
        'Weld Complete':    0.1,
        'Welded QC':        0.1,
        'Paint Start':      0.1,
        'Hold':             1.0,  # full hours, cascades off previous release
        'Paint Complete':   0.0,
        'Store at MHMW':    0.0,
        'Ship Planning':    0.0,
        'Ship Complete':    0.0,
        'Install Start':    0.0,
        'Install Complete': 0.0,
        'Complete':         0.0,
    }
    
    # Fabrication capacity (fixed daily capacity)
    FAB_HOURS_PER_DAY: float = 104.0  # 13 fabricators × 8 hrs/day
    
    # Installation capacity (fixed daily capacity).
    # Used as the fallback when a release has no crew size (num_guys) set —
    # equals 2 installers × 8 hrs/day, the legacy assumption.
    INSTALL_HOURS_PER_DAY: float = 16.0

    # Per-installer daily capacity. When a release has num_guys set, install
    # capacity = num_guys × HOURS_PER_PERSON_PER_DAY drives comp_eta.
    HOURS_PER_PERSON_PER_DAY: float = 8.0

    # Install buffer (working days between fab completion and install start)
    INSTALL_BUFFER_DAYS: int = 3
    
    @classmethod
    def get_stage_remaining_percentage(cls, stage: str) -> float:
        """
        Get the remaining fabrication percentage for a given stage.
        
        Args:
            stage: Stage name (e.g., 'Released', 'Cut Start', 'Fitup Complete', etc.)
            
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

