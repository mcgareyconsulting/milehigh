import requests
import re
import os
from app.config import Config as cfg


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


ids_and_names = get_all_card_ids(cfg.TRELLO_BOARD_ID)
if ids_and_names:
    print(f"First card ID: {ids_and_names[0][0]} | Name: {ids_and_names[0][1]}")

id = "6866a00ab050408017e0946c"

card_details = get_card_details(id)
print(f"Card details: {card_details}")


def get_card_stage_name(card_id):
    """
    Return the stage (list name) for a Trello card.
    """
    # Get card details
    card = get_card_details(card_id)
    list_id = card["idList"]

    # Get list details
    url = f"https://api.trello.com/1/lists/{list_id}"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    response.raise_for_status()
    list_data = response.json()
    return list_data["name"]


# Example usage:
stage_name = get_card_stage_name("6866a00ab050408017e0946c")
print(f"Stage name: {stage_name}")
