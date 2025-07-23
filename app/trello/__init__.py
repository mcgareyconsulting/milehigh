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
    if action.get("type") == "updateCard":
        print(f"Received action: {action['type']}")
        sync_from_trello(data)
    else:
        print(f"Unhandled action type: {action.get('type')}")

    return "", 200
