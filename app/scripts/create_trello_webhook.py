import requests
import os
from app.config import Config as cfg


def create_webhook_subscription():
    """
    Create a webhook subscription for Trello to monitor card movements.
    """
    response = requests.post(
        "https://api.trello.com/1/webhooks",
        params={
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
        },
        json={
            "description": "Track card moves",
            "callbackURL": cfg.TRELLO_WEBHOOK_URL,
            "idModel": cfg.TRELLO_BOARD_ID,
        },
    )

    print(response.status_code)
    print(response.json())


if __name__ == "__main__":
    create_webhook_subscription()
    print("Webhook subscription created successfully.")
