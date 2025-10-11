import requests
import re
import os
from app.config import Config as cfg
from app.trello.utils import mountain_due_datetime


# Main function for updating trello card information
def update_trello_card(card_id, new_list_id=None, new_due_date=None, clear_due_date=False):
    """
    Updates a Trello card\'s list and/or due date in a single API call.
    
    Args:
        card_id: Trello card ID
        new_list_id: New list ID (optional)
        new_due_date: New due date as datetime object (optional)
        clear_due_date: If True, explicitly clear the due date even if new_due_date is None
    """
    url = f"https://api.trello.com/1/cards/{card_id}"

    payload = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
    }

    if new_list_id:
        payload["idList"] = new_list_id

    # Handle due date
    if new_due_date:
        # Set due date to 6pm Mountain time, DST-aware
        payload["due"] = mountain_due_datetime(new_due_date)
    elif clear_due_date:
        # Explicitly clear the due date using empty string (Trello API requirement)
        payload["due"] = ""
    # If neither new_due_date nor clear_due_date, don't include 'due' parameter at all

    try:
        # Log the payload for debugging
        print(f"[TRELLO API] Updating card {card_id} with payload: {payload}")
        
        response = requests.put(url, params=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        print(f"[TRELLO API] Card {card_id} updated successfully")
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error updating card {card_id}: {http_err}")
        print("[TRELLO API] Response content:", response.text)
        raise
    except Exception as err:
        print(f"[TRELLO API] Other error updating card {card_id}: {err}")
        raise


## Helper functions for combining Trello and Excel data
def get_list_name_by_id(list_id):
    """
    Fetches the list name from Trello API by list ID.
    """
    url = f"https://api.trello.com/1/lists/{list_id}"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get("name")
    else:
        print(f"Trello API error: {response.status_code} {response.text}")
        return None


def get_list_by_name(list_name):
    """
    Fetches the list details from Trello API by list name.
    """
    url = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        lists = response.json()
        for lst in lists:
            if lst["name"] == list_name:
                return {"name": lst["name"], "id": lst["id"]}
    else:
        print(f"Trello API error: {response.status_code} {response.text}")
        return None


def get_trello_card_by_id(card_id):
    """
    Fetches the full card data from Trello API by card ID.
    """
    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Trello API error: {response.status_code} {response.text}")
        return None


def get_trello_cards_from_subset():
    """
    Fetch all Trello cards from the board and filter them based on a specific subset.
    """
    # Hardcoded list of stage names
    target_list_names = [
        "Fit Up Complete.",
        "Paint complete",
        "Shipping completed",
    ]

    # Get all lists on the board
    url_lists = url_lists = (
        f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
    )
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url_lists, params=params)
    response.raise_for_status()
    lists = response.json()

    # Get list IDs for your target lists
    target_list_ids = [lst["id"] for lst in lists if lst["name"] in target_list_names]

    # debug statement
    # print(f"Target List IDs: {target_list_ids}")

    # Get all cards on the board
    url_cards = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/cards"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "fields": "id,name,desc,idList,due,labels",
        "filter": "open",
    }
    response = requests.get(url_cards, params=params)
    response.raise_for_status()
    cards = response.json()

    # Build a mapping from list ID to list name
    list_id_to_name = {lst["id"]: lst["name"] for lst in lists}

    # Filter cards by your target list IDs
    filtered_cards = [card for card in cards if card["idList"] in target_list_ids]
    relevant_data = [
        {
            "id": card["id"],
            "name": card["name"],
            "desc": card["desc"],
            "list_id": card["idList"],
            "list_name": list_id_to_name.get(card["idList"], "Unknown"),
            "due": card.get("due"),
            "labels": [label["name"] for label in card.get("labels", [])],
        }
        for card in filtered_cards
    ]
    return relevant_data
