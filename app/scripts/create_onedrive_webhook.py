import requests
import os
import json
from datetime import datetime, timedelta
from app.config import Config as cfg
from app.sheets import get_access_token, get_drive_and_folder_id


def create_webhook_subscription():
    """Create a webhook subscription on the folder containing the Excel file."""
    print("🔍 Step 1: Getting access token...")
    access_token = get_access_token()

    print("🔍 Step 2: Getting drive_id and folder_id...")
    drive_id, folder_id = get_drive_and_folder_id()

    print("🔍 Step 3: Creating webhook subscription...")

    resource_path = f"/drives/{drive_id}/root"
    expiration = (datetime.utcnow() + timedelta(hours=23)).isoformat() + "Z"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "changeType": "updated",
        "notificationUrl": cfg.ONEDRIVE_WEBHOOK_URL,
        "resource": resource_path,
        "expirationDateTime": expiration,
        "clientState": "secretClientValue",
    }

    print(f"📤 Webhook URL: {cfg.ONEDRIVE_WEBHOOK_URL}")
    print(f"📤 Resource path: {resource_path}")

    response = requests.post(
        "https://graph.microsoft.com/v1.0/subscriptions",
        headers=headers,
        data=json.dumps(payload),
    )

    if response.status_code == 201:
        sub = response.json()
        print("\n✅ SUCCESS! Webhook subscription created!")
        print(f"📝 Subscription ID: {sub['id']}")
        print(f"⏰ Expires: {sub['expirationDateTime']}")
        return sub
    else:
        print(f"\n❌ FAILED to create subscription!")
        print(f"Status Code: {response.status_code}")
        print(f"Error: {response.text}")
        return None


if __name__ == "__main__":
    create_webhook_subscription()
