from app.trello.utils import extract_card_name, extract_identifier


def sync_from_trello(data):
    """Sync data from Trello to OneDrive based on the webhook payload."""
    print(data)
    # card name
    card_name = extract_card_name(data)
    print(f"Syncing card: {card_name}")

    # Get unique id
    identifier = extract_identifier(card_name)
    print(f"Extracted identifier: {identifier}")
