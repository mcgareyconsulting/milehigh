import requests
import re
import os
from app.config import Config as cfg
from app.trello.utils import mountain_due_datetime


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


def set_card_due_date(card_id, due_date):
    """
    Sets the due date of a Trello card.
    - card_id: Trello card ID
    - due_date: Python date or datetime object (will be formatted as ISO8601)
    """
    # Support both date and datetime input
    if due_date is None:
        print(f"[TRELLO] No due date supplied for card {card_id}; skipping update.")
        return False

    due_str = mountain_due_datetime(due_date)

    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN, "due": due_str}
    response = requests.put(url, params=params)
    if response.status_code == 200:
        print(f"[TRELLO] Set due date for card {card_id} to {due_str}")
        return True
    else:
        print(f"[TRELLO] API error ({response.status_code}): {response.text}")
        return False


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


def get_all_card_names(board_id):
    """
    Return a list of all card names on the board
    """
    url = f"https://api.trello.com/1/boards/{board_id}/cards"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    response.raise_for_status()
    cards = response.json()
    return [card["name"] for card in cards]


def get_all_card_ids(board_id):
    url = f"https://api.trello.com/1/boards/{board_id}/cards"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    response.raise_for_status()
    cards = response.json()
    return [(card["id"], card["name"]) for card in cards]


def get_card_details(card_id):
    """
    Return all data for a specific Trello card by card_id.
    """
    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


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


def move_card_to_list(card_id, list_id):
    """
    Move a Trello card to a different list.
    """
    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "idList": list_id,
    }
    response = requests.put(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Trello API error: {response.status_code} {response.text}")
        return None


# # Example usage:
# cards = get_trello_cards_from_subset()
# identifiers = extract_identifiers_from_cards(cards)

# for card_id, identifier in identifiers:
#     if identifier:
#         print(f"Card ID: {card_id}, Identifier: {identifier}")
#     else:
#         # Find the card name from cards list
#         card_name = next(
#             (card["name"] for card in cards if card["id"] == card_id), "Unknown"
#         )
#         print(f"Card ID: {card_id} has no valid identifier. Card name: {card_name}")
