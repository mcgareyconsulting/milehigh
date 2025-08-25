from flask import Blueprint, request
from app.sync import sync_from_trello

trello_bp = Blueprint("trello", __name__)


@trello_bp.route("/webhook", methods=["HEAD", "POST"])
def trello_webhook():
    """
    Webhook route to handle Trello card moves and any card data changes.
    """
    if request.method == "HEAD":
        return "", 200  # Trello webhook validation

    data = request.get_json(silent=True)
    if not data or "action" not in data:
        return "Invalid payload", 400

    action = data["action"]
    action_type = action.get("type")
    action_data = action.get("data", {})
    card_info = action_data.get("card", {})
    card_id = card_info.get("id")

    # Always print received action for debugging
    print(f"[Trello] Received action: {action_type} for card {card_id}")

    # Card moved between lists
    if (
        action_type == "updateCard"
        and "listBefore" in action_data
        and "listAfter" in action_data
    ):
        before = action_data["listBefore"]["name"]
        after = action_data["listAfter"]["name"]
        print(f"[Trello] Card {card_id} moved from '{before}' to '{after}'")

    # Card field changes (name, desc, due, labels, etc.)
    elif action_type == "updateCard":
        changed_fields = []
        for field in ["name", "desc", "due"]:
            if "old" in action_data and field in action_data["old"]:
                changed_fields.append(field)
        if "label" in action_data or "labels" in action_data:
            changed_fields.append("labels")
        if changed_fields:
            message = f"Card {card_id} changed: {', '.join(changed_fields)}"
            print(message)
            sync_from_trello(data)
            # Here you can trigger your upsert/diff logic
            # upsert_card(card_id, ...)

    # You can also handle createCard, deleteCard, archiveCard, etc., if needed

    return "", 200
