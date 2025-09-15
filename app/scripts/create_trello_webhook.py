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

    return response.json(), response.status_code


if __name__ == "__main__":
    response, code = create_webhook_subscription()
    if code == 200:
        print("Webhook subscription created successfully.")
    else:
        print(
            f"Failed to create webhook subscription: {response.get('error', 'Unknown error')}"
        )
