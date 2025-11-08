from app.config import Config as cfg
from app.trello.client import get_trello_client

## Helper functions for combining Trello and Excel data
def get_list_name_by_id(list_id):
    """
    Fetches the list name from Trello API by list ID.
    """
    trello = get_trello_client()
    response = trello.get(f"lists/{list_id}")
    return response.get("name") if response else None

def get_list_by_name(list_name):
    """
    Fetches the list details from Trello API by list name.
    """
    trello = get_trello_client()
    response = trello.get(f"boards/{cfg.TRELLO_BOARD_ID}/lists")
    return next((lst for lst in response if lst.get("name") == list_name), None)


def get_trello_card_by_id(card_id):
    """
    Fetches the full card data from Trello API by card ID.
    """
    trello = get_trello_client()
    response = trello.get(f"cards/{card_id}")
    return response if response else None

def get_card_custom_field_items(card_id):
    """
    Retrieves all custom field items for a Trello card.
    
    Args:
        card_id: Trello card ID
    
    Returns:
        List of custom field items or None if error
    """
    trello = get_trello_client()
    response = trello.get(f"cards/{card_id}/customFieldItems")
    return response if response else None

def get_board_custom_fields(board_id):
    """
    Get all custom fields for a Trello board.
    
    Args:
        board_id: Trello board ID
    
    Returns:
        List of custom field definitions or None if error
    """
    trello = get_trello_client()
    response = trello.get(f"boards/{board_id}/customFields")
    return response if response else None

if __name__ == "__main__":
    # print(get_list_name_by_id("68f266ac15e2986af8135114"))
    # print(get_list_by_name("Fit Up Complete."))
    print(get_trello_card_by_id("690a4aecefd93e453af10ee3"))
    print(get_card_custom_field_items("690a4aecefd93e453af10ee3"))
    print(get_board_custom_fields(cfg.TRELLO_BOARD_ID))