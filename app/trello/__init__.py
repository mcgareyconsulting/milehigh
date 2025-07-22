from flask import Blueprint, request
from app.sync import sync_from_trello

# setup for the Trello webhook blueprint
trello_bp = Blueprint("trello", __name__)


# Trello webhook route
@trello_bp.route("/webhook", methods=["HEAD", "POST"])
def trello_webhook():
    if request.method == "HEAD":
        return "", 200  # Trello's webhook validation ping

    data = request.json
    action = data.get("action", {})
    if action.get("type") == "updateCard":
        movement = action.get("data", {})
        if "listBefore" in movement and "listAfter" in movement:
            card_name = movement["card"]["name"]
            before = movement["listBefore"]["name"]
            after = movement["listAfter"]["name"]
            print(f"[Render] Card '{card_name}' moved from '{before}' to '{after}'.")
            sync_from_trello(data)  # Call the sync function to update OneDrive

    return "", 200
