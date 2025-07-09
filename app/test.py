import requests
import re
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID")


def get_all_card_names(board_id):
    """Return a list of all card names on the board"""
    url = f"https://api.trello.com/1/boards/{board_id}/cards"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    response = requests.get(url, params=params)
    response.raise_for_status()
    cards = response.json()
    return [card["name"] for card in cards]


def extract_identifiers(card_names):
    """
    Extracts the 6-7 digit identifier from the front of each card name.
    Returns a list of identifiers (as strings).
    """
    identifiers = []
    for name in card_names:
        match = re.match(r"(\d{3}-(?:\d{3}|V\d{3}))", name.strip(), re.IGNORECASE)
        if match:
            identifiers.append(match.group(1))
    return identifiers


def get_trello_identifiers():
    card_names = get_all_card_names(TRELLO_BOARD_ID)
    return extract_identifiers(card_names)
