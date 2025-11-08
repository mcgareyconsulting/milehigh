from app.config import Config as cfg
from app.trello.client import get_trello_client
from app.trello.helpers import sort_cards_by_fab_order, calculate_new_positions

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

def get_cards_in_list(list_id):
    """
    Get all cards in a Trello list, including custom field items.
    Args:
        list_id: Trello list ID
    
    Returns:
        List of cards or None if error
    """
    trello = get_trello_client()
    response = trello.get(f"lists/{list_id}/cards", params={"customFieldItems": "true", "fields": "id,pos,name"})
    return response if response else []

def sort_list_by_fab_order(list_id, fab_order_field_id):
    """
    Sort a Trello list by Fab Order custom field (ascending order).
    Cards without Fab Order values will be placed at the end.
    
    Args:
        list_id: Trello list ID to sort
        fab_order_field_id: Custom field ID for "Fab Order"
    
    Returns:
        dict with keys:
            - success: bool
            - cards_sorted: int (number of cards that were sorted)
            - cards_failed: int (number of cards that failed to update)
            - total_cards: int (total cards in list)
            - error: str (if success is False)
    """
    try:
        # Get all cards in the list with custom field items
        cards = get_cards_in_list(list_id)
        
        if not cards:
            print(f"[TRELLO API] List {list_id} is empty, nothing to sort")
            return {"success": True, "cards_sorted": 0, "cards_failed": 0, "total_cards": 0}

        sorted_cards = sort_cards_by_fab_order(cards, fab_order_field_id)
        positions = calculate_new_positions(sorted_cards)
        updated, failed = update_card_positions(positions)

        return {
            "success": True,
            "cards_sorted": updated,
            "cards_failed": failed,
            "total_cards": len(cards)
        }
    except Exception as err:
        error_msg = f"Error sorting list {list_id}: {err}"
        print(f"[TRELLO API] {error_msg}")
        return {"success": False, "error": error_msg, "cards_sorted": 0, "cards_failed": 0, "total_cards": 0}

def update_card_positions(position_updates):
    """Update cards in Trello and return counts."""
    client = get_trello_client()
    updated = 0 
    failed = 0

    for upd in position_updates:
        try:
            client.put(f"cards/{upd['card_id']}", params={"pos": upd["new_pos"]})
            updated += 1
        except Exception as e:
            print(f"[TRELLO API] Failed updating {upd['card_id']}: {e}")
            failed += 1

    return updated, failed

if __name__ == "__main__":
    # print(get_list_name_by_id("68f266ac15e2986af8135114"))
    # print(get_list_by_name("Fit Up Complete."))
    print(get_trello_card_by_id("690a4aecefd93e453af10ee3"))
    print(get_card_custom_field_items("690a4aecefd93e453af10ee3"))
    print(get_board_custom_fields(cfg.TRELLO_BOARD_ID))