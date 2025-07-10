import requests
import os
import json
from datetime import datetime, timedelta

# Replace with your actual access token logic
from app.sheets import get_access_token
from app.config import Config as cfg


def create_webhook():
    access_token = get_access_token()  # From your existing `sheets.py`

    callback_url = cfg.WEBHOOK_URL
    expiration = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Subscribe to the item (file) – this is commonly the Excel file
    payload = {
        "changeType": "updated",
        "notificationUrl": callback_url,
        "resource": "/me/drive/root:/Documents/your-excel.xlsx",  # Update to your actual file path
        "expirationDateTime": expiration,
        "clientState": "secretClientValue",  # Optional: use to validate source
    }

    response = requests.post(
        "https://graph.microsoft.com/v1.0/subscriptions",
        headers=headers,
        data=json.dumps(payload),
    )

    if response.status_code == 201:
        print("Subscription created:")
        print(json.dumps(response.json(), indent=2))
    else:
        print("Error creating subscription:")
        print(response.status_code, response.text)


if __name__ == "__main__":
    create_webhook()
