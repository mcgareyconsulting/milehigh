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
