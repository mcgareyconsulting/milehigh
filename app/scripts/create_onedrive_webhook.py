import requests
import os
import json
from datetime import datetime, timedelta

# Replace with your actual access token logic
from app.sheets import get_access_token, get_drive_and_item_id
from app.config import Config as cfg


def create_webhook_subscription():
    """Create the webhook subscription with drive_id and item_id"""
    print("🔍 Step 1: Getting access token...")
    access_token = get_access_token()

    print("🔍 Step 2: Finding file and getting drive_id + item_id...")
    drive_id, item_id = get_drive_and_item_id()

    print("🔍 Step 3: Creating webhook subscription...")

    # Build the resource path using drive_id and item_id
    resource_path = f"/drives/{drive_id}/items/{item_id}"

    # Webhook expires in 23 hours (max for OneDrive)
    expiration = (datetime.utcnow() + timedelta(hours=23)).isoformat() + "Z"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "changeType": "updated",
        "notificationUrl": cfg.WEBHOOK_URL,
        "resource": resource_path,
        "expirationDateTime": expiration,
        "clientState": "secretClientValue",
    }

    print(f"📤 Webhook URL: {cfg.WEBHOOK_URL}")
    print(f"📤 Resource path: {resource_path}")

    response = requests.post(
        "https://graph.microsoft.com/v1.0/subscriptions",
        headers=headers,
        data=json.dumps(payload),
    )

    if response.status_code == 201:
        subscription_data = response.json()
        print("\n✅ SUCCESS! Webhook subscription created!")
        print(f"📝 Subscription ID: {subscription_data['id']}")
        print(f"⏰ Expires: {subscription_data['expirationDateTime']}")
        print(f"🎯 Monitoring file: {cfg.ONEDRIVE_FILE_NAME}")
        return subscription_data
    else:
        print(f"\n❌ FAILED to create subscription!")
        print(f"Status Code: {response.status_code}")
        print(f"Error: {response.text}")
        return None


if __name__ == "__main__":
    try:
        create_webhook_subscription()
    except Exception as e:
        print(f"❌ Error: {str(e)}")
