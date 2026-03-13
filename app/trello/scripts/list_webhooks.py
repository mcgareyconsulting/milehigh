"""
Script to list all Trello webhooks for the current token.

Usage:
    python -m app.trello.scripts.list_webhooks

Lists all webhooks with ID, description, callbackURL, active status, and idModel.
"""

import requests
from dotenv import load_dotenv
import os

load_dotenv()


def list_webhooks():
    """List all webhooks for the current Trello token."""
    api_key = os.environ.get("TRELLO_API_KEY")
    token = os.environ.get("TRELLO_TOKEN")

    if not api_key or not token:
        print("Error: TRELLO_API_KEY and TRELLO_TOKEN must be set in .env")
        return

    url = f"https://api.trello.com/1/tokens/{token}/webhooks"
    params = {
        "key": api_key,
        "token": token,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()

        webhooks = response.json()

        if not webhooks:
            print("No webhooks found.")
            return

        print("=" * 100)
        print("TRELLO WEBHOOKS")
        print("=" * 100)
        print()

        for webhook in webhooks:
            webhook_id = webhook.get("id", "N/A")
            description = webhook.get("description", "N/A")
            callback_url = webhook.get("callbackURL", "N/A")
            active = webhook.get("active", "N/A")
            id_model = webhook.get("idModel", "N/A")

            print(f"ID: {webhook_id}")
            print(f"  Description: {description}")
            print(f"  Callback URL: {callback_url}")
            print(f"  Active: {active}")
            print(f"  Model ID: {id_model}")
            print()

        print("=" * 100)
        print(f"Total webhooks: {len(webhooks)}")

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        if e.response.status_code == 401:
            print("Error: Unauthorized. Check your TRELLO_API_KEY and TRELLO_TOKEN.")
        else:
            print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Main entry point."""
    list_webhooks()


if __name__ == "__main__":
    main()
