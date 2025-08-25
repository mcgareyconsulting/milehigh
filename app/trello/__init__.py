from flask import Blueprint, request
from app.sync import sync_from_trello
from app.trello.utils import parse_webhook_data

trello_bp = Blueprint("trello", __name__)


@trello_bp.route("/webhook", methods=["HEAD", "POST"])
def trello_webhook():
    """
    Webhook route to handle Trello card moves and any card data changes.
    """
    if request.method == "HEAD":
        return "", 200  # Trello webhook validation

    # Pass to data handler
    if request.method == "POST":
        data = request.json
        event_info = parse_webhook_data(data)
        print(f"Received Trello webhook event: {event_info}")

        # # Trigger sync process
        # sync_from_trello(event_info)

    return "", 200
