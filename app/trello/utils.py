import re
from datetime import datetime, timezone


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

        # Card moved between lists
        if (
            action_type == "updateCard"
            and "listBefore" in action_data
            and "listAfter" in action_data
        ):
            return {
                "event": "card_moved",
                "handled": True,
                "card_id": card_id,
                "card_name": card_name,
                "from": action_data["listBefore"]["name"],
                "to": action_data["listAfter"]["name"],
                "time": event_time,
            }

        # Card field changes (name, desc, due, labels, etc.)
        elif action_type == "updateCard":
            changed_fields = [
                field
                for field in ["name", "desc", "due"]
                if "old" in action_data and field in action_data["old"]
            ]
            if "label" in action_data or "labels" in action_data:
                changed_fields.append("labels")
            # Skip events that are only 'pos' changes
            if changed_fields and changed_fields != ["pos"]:
                return {
                    "event": "card_updated",
                    "handled": True,
                    "card_id": card_id,
                    "card_name": card_name,
                    "changed_fields": changed_fields,
                    "time": event_time,
                }

        # Other actions can be added here

        # If nothing above matched, it's unhandled
        return {"event": "unhandled", "handled": False, "details": data}
    except Exception as e:
        print(f"Error parsing webhook data: {e}")
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
