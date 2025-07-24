from flask import Blueprint, request
from app.sync import sync_from_trello

trello_bp = Blueprint("trello", __name__)


@trello_bp.route("/webhook", methods=["HEAD", "POST"])
def trello_webhook():
    if request.method == "HEAD":
        return "", 200  # Trello webhook validation ping

    data = request.get_json(silent=True)
    if not data or "action" not in data:
        return "Invalid payload", 400

    action = data["action"]
    action_type = action.get("type")
    action_data = action.get("data", {})

    print(f"Received Trello action: {action_type}")

    if action_type == "updateCard":
        # Track/log all updates
        card_id = action_data.get("card", {}).get("id", "unknown")
        print(f"Update on card {card_id}")

        # Only sync if the card moved lists
        if "listBefore" in action_data and "listAfter" in action_data:
            print(
                f"Card moved from {action_data['listBefore']['name']} to {action_data['listAfter']['name']}"
            )
            sync_from_trello(data)
        else:
            print("Card updated, but not moved lists. Ignoring.")
    else:
        print(f"Unhandled action type: {action_type}")

    return "", 200
