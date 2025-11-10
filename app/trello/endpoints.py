from app.config import Config as cfg
from app.trello.client import get_trello_client
from app.trello.helpers import sort_cards_by_fab_order, calculate_new_positions
from app.trello.utils import mountain_start_datetime, mountain_due_datetime

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



def update_card_custom_field_number(card_id, custom_field_id, number_value):
    """
    Updates a number custom field on a Trello card.
    
    Args:
        card_id: Trello card ID
        custom_field_id: Custom field ID
        number_value: Integer value for the custom field
    
    Returns:
        True if successful, False otherwise
    """
    trello = get_trello_client()
    payload = {
        "value": {"number": str(number_value)}
    }
    response = trello.put(f"cards/{card_id}/customField/{custom_field_id}/item", json=payload)
    return response.json() if response else None

def update_trello_card_description(card_id, new_description):
    """
    Update a Trello card's description via API.
    
    Args:
        card_id (str): Trello card ID
        new_description (str): New description text
        
    Returns:
        dict: Response from Trello API, or None if update fails
    """
    trello = get_trello_client()
    url = f"https://api.trello.com/1/cards/{card_id}"
    payload = {
        "desc": new_description
    }
    response = trello.put(f"cards/{card_id}", json=payload)
    return response.json() if response else None
        
def update_card_date_range(card_short_link, start_date, due_date):
    """
    Update a card's start and due dates.
    """
    try:
        trello = get_trello_client()
        start_date_str = mountain_start_datetime(start_date)
        due_date_str = mountain_due_datetime(due_date)

        params = {
            "start": start_date_str,
            "due": due_date_str,
        }

        print(f"[TRELLO API] Updating mirror card {card_short_link} with start: {start_date_str}, due: {due_date_str}")
        response = trello.put(f"cards/{card_short_link}", params=params)

        if response:
            print(f"[TRELLO API] Successfully updated mirror card {card_short_link}")
            return {
                "success": True,
                "card_short_link": card_short_link,
                "start_date": start_date_str,
                "due_date": due_date_str,
            }

        print(f"[TRELLO API] Error updating mirror card {card_short_link}")
        return {
            "success": False,
            "error": "Trello API error: request failed",
        }

    except Exception as e:
        error_msg = f"Error updating card date range: {str(e)}"
        print(f"[TRELLO API] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
        }
        
def add_procore_link(card_id, procore_url, link_name=None):
    """
    Add a Procore link as an attachment to a Trello card.
    """
    if not procore_url or not procore_url.strip():
        print(f"[TRELLO API] Skipping empty Procore URL for card {card_id}")
        return {
            "success": False,
            "error": "Procore URL is required",
        }

    trello = get_trello_client()
    params = {
        "url": procore_url.strip(),
        "name": link_name or "FC Drawing - Procore Link",
    }

    try:
        print(f"[TRELLO API] Adding Procore link to card {card_id}: {procore_url[:100]}...")
        attachment_data = trello.post(f"cards/{card_id}/attachments", params=params)

        if not attachment_data:
            print(f"[TRELLO API] Request failed while adding Procore link to card {card_id}")
            return {
                "success": False,
                "error": "Trello API error: request failed",
            }

        print(f"[TRELLO API] Procore link added successfully (attachment ID: {attachment_data.get('id')})")
        return {
            "success": True,
            "card_id": card_id,
            "attachment_id": attachment_data.get("id"),
            "attachment_url": attachment_data.get("url"),
            "attachment_name": attachment_data.get("name"),
        }

    except Exception as err:
        print(f"[TRELLO API] Error adding Procore link: {err}")
        return {
            "success": False,
            "error": str(err),
        }

if __name__ == "__main__":
    # print(get_list_name_by_id("68f266ac15e2986af8135114"))
    # print(get_list_by_name("Fit Up Complete."))
    print(get_trello_card_by_id("690a4aecefd93e453af10ee3"))
    print(get_card_custom_field_items("690a4aecefd93e453af10ee3"))
    print(get_board_custom_fields(cfg.TRELLO_BOARD_ID))