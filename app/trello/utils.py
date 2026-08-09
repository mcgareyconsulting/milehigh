"""
@milehigh-header
schema_version: 1
purpose: Pure-logic utilities (webhook parsing, date math, identifier extraction, Fab-Order sorting) shared across the Trello package with no DB writes.
exports:
  parse_webhook_data: Parse raw Trello webhook JSON into a normalised event dict.
  parse_trello_datetime: Convert Trello ISO-8601 strings to naive Python datetimes.
  extract_identifier: Pull the "NNN-NNN" job-release prefix from a card name.
  mountain_due_datetime: Convert a local date to 6 pm Mountain ISO string for Trello due dates.
  CALENDAR_FIELD / CALENDAR_SHOP / is_business_day: N4 two-calendar model.
  add_business_days / calculate_business_days_before: working-day math with calendar=.
  should_sort_list_by_fab_order: Decide whether a list needs Fab-Order re-sorting.
  sort_list_if_needed: Sort a list by Fab Order if it is a target list, with logging.
imports_from: [app.config, app.trello.api, app.trello.logging, app.logging_config, zoneinfo, re]
imported_by: [app/trello/sync.py, app/trello/scanner.py, app/trello/card_creation.py, app/trello/api.py, app/brain/job_log/routes.py, app/services/outbox_service.py]
invariants:
  - parse_webhook_data never raises; errors return {"event": "error", "handled": False}.
  - All Mountain-time conversions are DST-aware via ZoneInfo.
  - Default calendar is FIELD (Mon–Fri); SHOP is Mon–Thu (fab + paint).
updated_by_agent: 2026-08-09T00:00:00Z
"""

import re
from datetime import datetime, date, timezone, time, timedelta
from zoneinfo import ZoneInfo

from app.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# N4 — two working calendars (docs/roadmap.md)
# ---------------------------------------------------------------------------
# SHOP  — fabrication + paint: Mon–Thu, 4×10s (Fridays off)
# FIELD — ship + install (+ drafting/admin default): Mon–Fri
# Default for helpers is FIELD so un-audited call sites keep prior Mon–Fri behavior.
CALENDAR_FIELD = "field"
CALENDAR_SHOP = "shop"

_CALENDAR_MAX_WEEKDAY = {
    CALENDAR_FIELD: 4,  # Mon–Fri (weekday 0–4)
    CALENDAR_SHOP: 3,   # Mon–Thu (weekday 0–3)
}


def is_business_day(d, calendar=CALENDAR_FIELD) -> bool:
    """True if ``d`` is a working day on the given calendar (no holiday table yet)."""
    if isinstance(d, datetime):
        d = d.date()
    max_wd = _CALENDAR_MAX_WEEKDAY.get(calendar)
    if max_wd is None:
        raise ValueError(
            f"unknown calendar {calendar!r}; use CALENDAR_FIELD or CALENDAR_SHOP"
        )
    return d.weekday() <= max_wd


def parse_webhook_data(data):
    """
    Parses Trello webhook data to extract relevant Trello events.
    Returns a dict describing the event type and data.
    """
    try:
        action = data.get("action", {})
        action_type = action.get("type")
        action_data = action.get("data", {})
        card_info = action_data.get("card", {})
        card_id = card_info.get("id")
        card_name = card_info.get("name")
        event_time = action.get("date")
        
        # Extract username and userId from memberCreator (prefer fullName, fallback to username)
        member_creator = action.get("memberCreator", {})
        username = member_creator.get("fullName") or member_creator.get("username") or None
        # Trello user ID (e.g. "50e853a3a98492ed05002257") for release event attribution
        trello_user_id = member_creator.get("id") or action.get("idMemberCreator") or None

        # Card created
        if action_type == "createCard":
            list_info = action_data.get("list", {})
            list_name = list_info.get("name")
            list_id = list_info.get("id")
            
            return {
                "event": "card_created",
                "handled": True,
                "card_id": card_id,
                "card_name": card_name,
                "list_id": list_id,
                "list_name": list_name,
                "time": event_time,
                "username": username,
            }

        # Card update - check for list move, due date change, description change, and combinations
        elif action_type == "updateCard":
            # Detect list move
            list_move = "listBefore" in action_data and "listAfter" in action_data
            list_from = action_data["listBefore"]["name"] if list_move else None
            list_to = action_data["listAfter"]["name"] if list_move else None
            
            # Detect field changes from 'old' data
            old_data = action_data.get("old", {})
            due_date_change = "due" in old_data
            start_date_change = "start" in old_data
            description_change = "desc" in old_data

            # Check if there are other field changes (name, labels, etc.)
            name_change = "name" in old_data
            label_change = "label" in action_data or "labels" in action_data

            # Build list of change types
            change_types = []
            if list_move:
                change_types.append("list_move")
            if due_date_change:
                change_types.append("due_date_change")
            if start_date_change:
                change_types.append("start_date_change")
            if description_change:
                change_types.append("description_change")
            if name_change:
                change_types.append("name_change")
            if label_change:
                change_types.append("label_change")
            
            # Skip events that are only 'pos' changes or have no relevant changes
            if change_types:
                result = {
                    "event": "card_updated",
                    "handled": True,
                    "card_id": card_id,
                    "card_name": card_name,
                    "time": event_time,
                    "change_types": change_types,
                    "username": username,
                    "trello_user_id": trello_user_id,
                }
                
                # Add specific flags for easier handling
                result["has_list_move"] = list_move
                result["has_due_date_change"] = due_date_change
                result["has_start_date_change"] = start_date_change
                result["has_description_change"] = description_change
                
                # Add list move details if applicable
                if list_move:
                    result["from"] = list_from
                    result["to"] = list_to
                    result["list_id_before"] = action_data["listBefore"]["id"]
                    result["list_id_after"] = action_data["listAfter"]["id"]
                
                # Determine if Excel update is needed
                # Only list moves should be reflected back to Excel
                result["needs_excel_update"] = bool(list_move)
                
                return result

        # Other actions can be added here

        # If nothing above matched, it's unhandled
        return {"event": "unhandled", "handled": False, "details": data, "action_type": action_type}
    except Exception as e:
        logger.error(
            "webhook_parse_failed",
            source="trello",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return {"event": "error", "handled": False, "error": str(e)}


def parse_trello_datetime(dt_str):
    # Trello gives ISO8601 string with trailing Z for UTC or with offset
    if not dt_str:
        return None
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1]  # Remove the 'Z'
        dt = datetime.fromisoformat(dt_str)
        dt = dt.replace(tzinfo=None)  # Remove timezone info, make naive
        return dt
    else:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)  # Remove timezone info, make naive
        return dt


def extract_card_name(data):
    """
    Safely extracts the card name from a Trello webhook payload.
    Returns the card name as a string, or None if not found.
    """
    try:
        return data["action"]["display"]["entities"]["card"]["text"]
    except (KeyError, TypeError):
        return None


def extract_identifier(card_name):
    """
    Extracts a 6- or 7-digit identifier (e.g., 123-456 or 123-V456) only if it appears at the beginning of the card name.
    Returns the identifier as a string, or None if not found.
    """
    pattern = re.compile(r"^(?:\d{3}-\d{3}|\d{3}-V\d{3})", re.IGNORECASE)
    if not card_name:
        return None
    match = pattern.match(card_name.strip())
    return match.group(0) if match else None


def mountain_due_datetime(local_date):
    """
    Given a date or datetime, return ISO8601 string for 6pm Mountain time, converted to UTC.
    """
    # If it's already a datetime, just use the date part
    if isinstance(local_date, datetime):
        d = local_date.date()
    else:
        d = local_date

    # Combine with 6pm time
    dt_mountain = datetime.combine(d, time(6, 0))
    dt_mountain = dt_mountain.replace(tzinfo=ZoneInfo("America/Denver"))

    # Convert to UTC
    dt_utc = dt_mountain.astimezone(ZoneInfo("UTC"))
    # Format as Trello expects (ISO with Z)
    return dt_utc.isoformat().replace("+00:00", "Z")


def mountain_start_datetime(local_date):
    """
    Given a date or datetime, return ISO8601 string for 9am Mountain time, converted to UTC.
    Used for start dates (as opposed to due dates which use 6pm).
    """
    # If it's already a datetime, just use the date part
    if isinstance(local_date, datetime):
        d = local_date.date()
    else:
        d = local_date

    # Combine with 9am time
    dt_mountain = datetime.combine(d, time(9, 0))
    dt_mountain = dt_mountain.replace(tzinfo=ZoneInfo("America/Denver"))

    # Convert to UTC
    dt_utc = dt_mountain.astimezone(ZoneInfo("UTC"))
    # Format as Trello expects (ISO with Z)
    return dt_utc.isoformat().replace("+00:00", "Z")


def calculate_business_days_before(target_date, business_days=2, calendar=CALENDAR_FIELD):
    """
    Calculate the date that is a specified number of business days before the target date.

    Args:
        target_date: The target date (date or datetime object)
        business_days: Number of business days to go back (default: 2)
        calendar: CALENDAR_FIELD (Mon–Fri, default) or CALENDAR_SHOP (Mon–Thu)

    Returns:
        date: The calculated date that is business_days before target_date
    """
    if isinstance(target_date, datetime):
        current_date = target_date.date()
    else:
        current_date = target_date

    if not business_days or business_days <= 0:
        return current_date

    days_back = 0
    business_days_counted = 0

    while business_days_counted < business_days:
        days_back += 1
        check_date = current_date - timedelta(days=days_back)
        if is_business_day(check_date, calendar=calendar):
            business_days_counted += 1

    return current_date - timedelta(days=days_back)


def add_business_days(start_date, business_days, calendar=CALENDAR_FIELD):
    """
    Calculate the date that is a specified number of business days after the start date.

    Args:
        start_date: The start date (date or datetime object)
        business_days: Number of business days to add
        calendar: CALENDAR_FIELD (Mon–Fri, default) or CALENDAR_SHOP (Mon–Thu)

    Returns:
        date: The calculated date that is business_days after start_date
    """
    if isinstance(start_date, datetime):
        current_date = start_date.date()
    else:
        current_date = start_date

    if not business_days or business_days <= 0:
        return current_date

    days_forward = 0
    business_days_counted = 0

    while business_days_counted < business_days:
        days_forward += 1
        check_date = current_date + timedelta(days=days_forward)
        if is_business_day(check_date, calendar=calendar):
            business_days_counted += 1

    return current_date + timedelta(days=days_forward)


def should_sort_list_by_fab_order(list_id):
    """
    Check if a list should be sorted by Fab Order.
    Sorts 'Released' and 'Fit Up Complete.'lists.
    
    Args:
        list_id: Trello list ID to check
    
    Returns:
        bool: True if list should be sorted
    """
    from app.config import Config as cfg
    from app.trello.api import get_list_name_by_id
    
    # Target list names that should be sorted by Fab Order
    target_list_names = ["Released", "Fit Up Complete."]
    
    # First check config IDs for backward compatibility
    if list_id in (cfg.FIT_UP_COMPLETE_LIST_ID, cfg.NEW_TRELLO_CARD_LIST_ID):
        return True
    
    # Also check by list name to handle cases where config IDs might not be set
    try:
        list_name = get_list_name_by_id(list_id)
        if list_name in target_list_names:
            return True
    except Exception:
        # If we can't get the list name, fall back to config ID check only
        pass
    
    return False


def sort_list_if_needed(list_id, fab_order_field_id, operation_id, list_type="list"):
    """
    Sort a list by Fab Order if it's one of the target lists.
    
    Args:
        list_id: Trello list ID
        fab_order_field_id: Custom field ID for Fab Order
        operation_id: Operation ID for logging (can be None)
        list_type: Description of the list (e.g., "destination", "source", "list")
    
    Returns:
        bool: True if sort was attempted and successful
    """
    from app.trello.api import sort_list_by_fab_order
    from app.trello.logging import safe_log_sync_event
    
    if not should_sort_list_by_fab_order(list_id):
        return False
    
    sort_result = sort_list_by_fab_order(list_id, fab_order_field_id)
    if sort_result.get("success"):
        if operation_id:
            safe_log_sync_event(
                operation_id,
                "INFO",
                f"{list_type.capitalize()} list sorted by Fab Order",
                list_id=list_id,
                cards_sorted=sort_result.get("cards_sorted", 0)
            )
        else:
            logger.info(
                "list_sorted_by_fab_order",
                list_id=list_id,
                list_type=list_type,
                count=sort_result.get("cards_sorted", 0),
            )
        return True
    else:
        if operation_id:
            safe_log_sync_event(
                operation_id,
                "WARNING",
                f"{list_type.capitalize()} list sort failed",
                list_id=list_id,
                error=sort_result.get("error", "Unknown error")
            )
        else:
            logger.warning(
                "list_sort_failed",
                list_id=list_id,
                list_type=list_type,
                error=sort_result.get("error", "Unknown error"),
            )
        return False

