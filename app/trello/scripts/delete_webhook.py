"""
Script to delete Trello webhooks.

Usage:
    # Delete a specific webhook by ID
    python -m app.trello.scripts.delete_webhook --webhook-id <id>

    # Delete all webhooks for the token (with confirmation)
    python -m app.trello.scripts.delete_webhook --all

Requires confirmation before deleting to prevent accidental deletion.
"""

import argparse
import requests
from dotenv import load_dotenv
import os

load_dotenv()


def get_all_webhooks():
    """Get all webhooks for the current token."""
    api_key = os.environ.get("TRELLO_API_KEY")
    token = os.environ.get("TRELLO_TOKEN")

    if not api_key or not token:
        print("Error: TRELLO_API_KEY and TRELLO_TOKEN must be set in .env")
        return None

    url = f"https://api.trello.com/1/tokens/{token}/webhooks"
    params = {
        "key": api_key,
        "token": token,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching webhooks: {e}")
        return None


def delete_webhook(webhook_id):
    """Delete a specific webhook by ID."""
    api_key = os.environ.get("TRELLO_API_KEY")
    token = os.environ.get("TRELLO_TOKEN")

    if not api_key or not token:
        print("Error: TRELLO_API_KEY and TRELLO_TOKEN must be set in .env")
        return False

    url = f"https://api.trello.com/1/webhooks/{webhook_id}"
    params = {
        "key": api_key,
        "token": token,
    }

    try:
        response = requests.delete(url, params=params)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        print(f"Error deleting webhook {webhook_id}: {e}")
        if e.response.status_code == 404:
            print("Webhook not found.")
        else:
            print(f"Response: {e.response.text}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def delete_single_webhook(webhook_id):
    """Delete a single webhook with confirmation."""
    print(f"Delete webhook: {webhook_id}")
    print("WARNING: This will delete the webhook permanently!")
    print()

    response = input("Are you sure you want to delete this webhook? (yes/no): ")
    if response.lower() != "yes":
        print("Cancelled.")
        return False

    print("-" * 60)

    if delete_webhook(webhook_id):
        print("✓ Webhook deleted successfully!")
        return True
    else:
        print("✗ Failed to delete webhook.")
        return False


def delete_all_webhooks():
    """Delete all webhooks with confirmation."""
    webhooks = get_all_webhooks()

    if webhooks is None:
        return False

    if not webhooks:
        print("No webhooks found.")
        return True

    print(f"Found {len(webhooks)} webhook(s):")
    for webhook in webhooks:
        print(f"  - {webhook.get('id')}: {webhook.get('description', 'N/A')}")

    print()
    print("WARNING: This will delete ALL webhooks permanently!")
    print()

    response = input("Are you sure you want to delete all webhooks? (yes/no): ")
    if response.lower() != "yes":
        print("Cancelled.")
        return False

    print("-" * 60)

    deleted_count = 0
    error_count = 0

    for webhook in webhooks:
        webhook_id = webhook.get("id")
        description = webhook.get("description", "N/A")

        if delete_webhook(webhook_id):
            print(f"✓ Deleted: {webhook_id} ({description})")
            deleted_count += 1
        else:
            print(f"✗ Failed: {webhook_id} ({description})")
            error_count += 1

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Deleted: {deleted_count}")
    print(f"Errors: {error_count}")

    return error_count == 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Delete Trello webhooks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete a specific webhook by ID
  python -m app.trello.scripts.delete_webhook --webhook-id 5f1a2b3c4d5e6f7g8h9i0j1k

  # Delete all webhooks for the token
  python -m app.trello.scripts.delete_webhook --all
        """
    )

    parser.add_argument(
        "--webhook-id",
        help="Webhook ID to delete"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Delete all webhooks for the token"
    )

    args = parser.parse_args()

    if args.webhook_id and args.all:
        print("Error: Cannot use both --webhook-id and --all")
        return

    if not args.webhook_id and not args.all:
        print("Error: Must use either --webhook-id or --all")
        return

    if args.webhook_id:
        delete_single_webhook(args.webhook_id)
    elif args.all:
        delete_all_webhooks()


if __name__ == "__main__":
    main()
