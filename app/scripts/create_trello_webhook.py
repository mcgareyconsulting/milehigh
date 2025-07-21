import requests
import os
from app.config import Config as cfg

# Webhook creation for Trello
response = requests.post(
    "https://api.trello.com/1/webhooks",
    params={
        "key": cfg.API_KEY,
        "token": cfg.TOKEN,
    },
    json={
        "description": "Track card moves",
        "callbackURL": cfg.TRELLO_WEBHOOK_URL,
        "idModel": cfg.BOARD_ID,
    },
)

print(response.status_code)
print(response.json())
