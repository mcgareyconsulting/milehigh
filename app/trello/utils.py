import re


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
    Extracts the 6- or 7-digit identifier from the front of a card name.
    Returns the identifier as a string, or None if not found.
    """
    if not card_name:
        return None
    match = re.match(r"(\d{3}-(?:\d{3}|V\d{3}))", card_name.strip(), re.IGNORECASE)
    return match.group(1) if match else None
