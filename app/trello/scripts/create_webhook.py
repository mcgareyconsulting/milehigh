"""
Script to create a Trello webhook.

Usage:
    python -m app.trello.scripts.create_webhook [--callback-url <url>] [--board-id <id>] --description <desc>

Creates a webhook that will POST events to the specified callback URL when cards in the board change.
"""

import argparse
import requests
from dotenv import load_dotenv
import os

load_dotenv()


def create_webhook(callback_url, board_id, description):
    """Create a webhook for a Trello board."""
    api_key = os.environ.get("TRELLO_API_KEY")
    token = os.environ.get("TRELLO_TOKEN")

    if not api_key or not token:
        print("Error: TRELLO_API_KEY and TRELLO_TOKEN must be set in .env")
        return False

    url = "https://api.trello.com/1/webhooks/"

    payload = {
        "key": api_key,
        "token": token,
        "callbackURL": callback_url,
        "idModel": board_id,
        "description": description,
    }

    try:
        print(f"Creating webhook for board {board_id}...")
        print(f"  Callback URL: {callback_url}")
        print(f"  Description: {description}")
        print("-" * 60)

        response = requests.post(url, json=payload)
        response.raise_for_status()

        webhook = response.json()

        print("✓ Webhook created successfully!")
        print()
        print("=" * 60)
        print("WEBHOOK DETAILS")
        print("=" * 60)
        print(f"ID: {webhook.get('id')}")
        print(f"Description: {webhook.get('description')}")
        print(f"Callback URL: {webhook.get('callbackURL')}")
        print(f"Active: {webhook.get('active')}")
        print(f"Model ID: {webhook.get('idModel')}")
        print()

        return True

    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP Error: {e}")
        if e.response.status_code == 401:
            print("Error: Unauthorized. Check your TRELLO_API_KEY and TRELLO_TOKEN.")
        elif e.response.status_code == 400:
            print(f"Error: Bad request. {e.response.text}")
        else:
            print(f"Response: {e.response.text}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create a Trello webhook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create webhook with default board ID from env
  python -m app.trello.scripts.create_webhook --description "My webhook"

  # Create webhook with custom callback URL and board ID
  python -m app.trello.scripts.create_webhook \\
    --callback-url https://myapp.com/webhook/trello \\
    --board-id 5f1a2b3c4d5e6f7g8h9i0j1k \\
    --description "Production webhook"
        """
    )

    parser.add_argument(
        "--callback-url",
        help="Webhook callback URL (default: TRELLO_WEBHOOK_URL from env)"
    )
    parser.add_argument(
        "--board-id",
        help="Board ID to watch (default: TRELLO_BOARD_ID from env)"
    )
    parser.add_argument(
        "--description",
        required=True,
        help="Webhook description"
    )

    args = parser.parse_args()

    # Use env defaults if not provided
    callback_url = args.callback_url or os.environ.get("TRELLO_WEBHOOK_URL")
    board_id = args.board_id or os.environ.get("TRELLO_BOARD_ID")

    if not callback_url:
        print("Error: --callback-url required or TRELLO_WEBHOOK_URL must be set in .env")
        return

    if not board_id:
        print("Error: --board-id required or TRELLO_BOARD_ID must be set in .env")
        return

    create_webhook(callback_url, board_id, args.description)


if __name__ == "__main__":
    main()
