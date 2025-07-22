def sync_from_trello(data):
    """Sync data from Trello to OneDrive based on the webhook payload."""
    print(data)
    # Parse Trello webhook payload
    card_id = data.get("action", {}).get("data", {}).get("card", {}).get("text")
    print("Card ID:", card_id)
    # # Call OneDrive-related functions here
    # from app.sheets import update_excel_with_trello_data

    # update_excel_with_trello_data(card_id)
