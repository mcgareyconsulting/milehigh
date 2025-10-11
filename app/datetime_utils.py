"""
DateTime utility functions for the application.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def format_datetime_mountain(dt):
    """
    Format a datetime object to Mountain Time with readable format.
    Returns format like: "October 15, 2025 02:30:45 PM"
    
    Args:
        dt: datetime object, ISO string, or None
        
    Returns:
        str: Formatted datetime string in Mountain Time, or None if dt is None
    """
    if not dt:
        return None
    
    # Handle string input (ISO format)
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            return str(dt)  # Return as-is if parsing fails
    
    # Convert to Mountain Time
    mountain_tz = ZoneInfo("America/Denver")
    
    # If dt is naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Mountain Time
    mountain_dt = dt.astimezone(mountain_tz)
    
    # Format as requested: "October XX, YYYY 00:00:00 AM/PM"
    return mountain_dt.strftime("%B %d, %Y %I:%M:%S %p")


def format_datetime_utc(dt):
    """
    Format a datetime object to UTC with readable format.
    Returns format like: "October 15, 2025 02:30:45 PM UTC"
    
    Args:
        dt: datetime object, ISO string, or None
        
    Returns:
        str: Formatted datetime string in UTC, or None if dt is None
    """
    if not dt:
        return None
    
    # Handle string input (ISO format)
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            return str(dt)  # Return as-is if parsing fails
    
    # If dt is naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Ensure it's in UTC
    utc_dt = dt.astimezone(timezone.utc)
    
    # Format with UTC indicator
    return utc_dt.strftime("%B %d, %Y %I:%M:%S %p UTC")


def get_mountain_timezone():
    """
    Get the Mountain Time timezone object.
    
    Returns:
        ZoneInfo: Mountain Time timezone object
    """
    return ZoneInfo("America/Denver")
