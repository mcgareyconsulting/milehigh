from flask import Flask, request
from .config import Config


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return "Welcome to the Trello SharePoint Integration!"

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
