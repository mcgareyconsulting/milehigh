from app.trello import extract_card_text


def sync_from_trello(data):
    """Sync data from Trello to OneDrive based on the webhook payload."""
    print(data)
    # Parse Trello webhook payload
    card_name = extract_card_text(data)
    print(f"Syncing card: {card_name}")
