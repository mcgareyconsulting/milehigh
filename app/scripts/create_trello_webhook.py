import requests
import os

API_KEY = os.getenv("TRELLO_API_KEY")
TOKEN = os.getenv("TRELLO_TOKEN")
BOARD_ID = os.getenv("TRELLO_BOARD_ID")
CALLBACK_URL = "https://milehightrelloexcel.onrender.com/trello/webhook"

response = requests.post(
    "https://api.trello.com/1/webhooks",
    params={
        "key": API_KEY,
        "token": TOKEN,
    },
    json={
        "description": "Track card moves",
        "callbackURL": CALLBACK_URL,
        "idModel": BOARD_ID,
    },
)

print(response.status_code)
print(response.json())
