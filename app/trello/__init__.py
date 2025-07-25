from flask import Blueprint, request

trello_bp = Blueprint("trello", __name__)


@trello_bp.route("/webhook", methods=["HEAD", "POST"])
def trello_webhook():
    """
    Webhook route to collect Trello card movements
    This route handles both the initial validation request from Trello
    and the actual card movement notifications.
    The HEAD request is used for Trello's webhook validation ping.
    """
    if request.method == "HEAD":
        return "", 200  # Trello webhook validation ping

    data = request.get_json(silent=True)
    if not data or "action" not in data:
        return "Invalid payload", 400

    # Filtering down to card movement only for now
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

        from app.sync import sync_from_trello

        sync_from_trello(data)  # pass collected data to sync function

    # Quietly ignore all other actions
    return "", 200
