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

    # Only process card list moves
    if (
        action_type == "updateCard"
        and "listBefore" in action_data
        and "listAfter" in action_data
    ):
        card_id = action_data.get("card", {}).get("id")
        before = action_data["listBefore"]["name"]
        after = action_data["listAfter"]["name"]
        print(f"[Trello] Card {card_id} moved from '{before}' to '{after}'")
        sync_from_trello(data)

    # Quietly ignore all other actions
    return "", 200
