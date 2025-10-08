import requests
import os
from app.config import Config as cfg


def list_webhooks():
    """
    List all existing webhook subscriptions for the Trello API key/token.
    """
    response = requests.get(
        "https://api.trello.com/1/tokens/{}/webhooks".format(cfg.TRELLO_TOKEN),
        params={
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
        }
    )
    
    if response.status_code == 200:
        return response.json(), response.status_code
    else:
        return response.text, response.status_code


def delete_webhook(webhook_id):
    """
    Delete a specific webhook subscription by ID.
    """
    response = requests.delete(
        f"https://api.trello.com/1/webhooks/{webhook_id}",
        params={
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
        }
    )
    
    return response.json() if response.status_code == 200 else response.text, response.status_code


def delete_all_webhooks():
    """
    Delete all existing webhook subscriptions for the Trello API key/token.
    """
    webhooks, status = list_webhooks()
    
    if status != 200:
        print(f"Failed to list webhooks: {webhooks}")
        return
    
    if not webhooks:
        print("No webhooks found to delete.")
        return
    
    print(f"Found {len(webhooks)} webhook(s) to delete:")
    
    deleted_count = 0
    for webhook in webhooks:
        webhook_id = webhook.get('id')
        description = webhook.get('description', 'No description')
        callback_url = webhook.get('callbackURL', 'No URL')
        
        print(f"  - ID: {webhook_id}, Description: {description}, URL: {callback_url}")
        
        result, code = delete_webhook(webhook_id)
        if code == 200:
            print(f"    ✓ Deleted webhook {webhook_id}")
            deleted_count += 1
        else:
            print(f"    ✗ Failed to delete webhook {webhook_id}: {result}")
    
    print(f"\nDeleted {deleted_count} out of {len(webhooks)} webhook(s).")


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
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "delete":
        if len(sys.argv) > 2 and sys.argv[2] == "all":
            delete_all_webhooks()
        elif len(sys.argv) > 2:
            # Delete specific webhook by ID
            webhook_id = sys.argv[2]
            result, code = delete_webhook(webhook_id)
            if code == 200:
                print(f"Webhook {webhook_id} deleted successfully.")
            else:
                print(f"Failed to delete webhook {webhook_id}: {result}")
        else:
            print("Usage: python create_trello_webhook.py delete [webhook_id|all]")
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        webhooks, status = list_webhooks()
        if status == 200:
            print(f"Found {len(webhooks)} webhook(s):")
            for webhook in webhooks:
                print(f"  - ID: {webhook.get('id')}, Description: {webhook.get('description')}, URL: {webhook.get('callbackURL')}")
        else:
            print(f"Failed to list webhooks: {webhooks}")
    else:
        # Default behavior: create webhook
        response, code = create_webhook_subscription()
        if code == 200:
            print("Webhook subscription created successfully.")
        else:
            print(
                f"Failed to create webhook subscription: {response.get('error', 'Unknown error')}"
            )
