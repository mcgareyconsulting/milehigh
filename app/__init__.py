from flask import Flask, request
from .config import Config as cfg


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        message = f"Welcome to TSI {cfg.TRELLO_BOARD_ID} {cfg.TRELLO_API_KEY} {cfg.TRELLO_TOKEN} {cfg.AZURE_CLIENT_ID} {cfg.AZURE_CLIENT_SECRET} {cfg.AZURE_TENANT_ID} {cfg.WEBHOOK_URL}"

        return message

    @app.route("/trello/webhook", methods=["HEAD", "POST"])
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
                print(
                    f"[Render] Card '{card_name}' moved from '{before}' to '{after}'."
                )

        return "", 200

    return app
