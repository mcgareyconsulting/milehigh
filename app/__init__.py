from flask import Flask, request
from .config import Config as cfg
from routes.trello_webhook import trello_bp


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return "Trello SharePoint Integration is running!"

    app.register_blueprint(trello_bp, url_prefix="/trello")

    return app
