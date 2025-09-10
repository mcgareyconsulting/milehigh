from flask import Blueprint, request, current_app
from app.sync import sync_from_trello
from app.trello.utils import parse_webhook_data
import threading

trello_bp = Blueprint("trello", __name__)


@trello_bp.route("/webhook", methods=["HEAD", "POST"])
def trello_webhook():
    """
    Webhook route to handle Trello card moves and any card data changes.
    """
    if request.method == "HEAD":
        return "", 200  # Trello webhook validation

    if request.method == "POST":
        data = request.json
        event_info = parse_webhook_data(data)

        # Grab a reference to the app
        app = current_app._get_current_object()

        # Run sync in a background thread, but with app context
        def run_sync():
            with app.app_context():
                try:
                    sync_from_trello(event_info)
                except Exception as e:
                    # Log the error - sync failures will be silent otherwise
                    app.logger.error(f"Sync failed: {e}")

        threading.Thread(target=run_sync).start()

    # Immediate ACK to Trello
    return "", 200
