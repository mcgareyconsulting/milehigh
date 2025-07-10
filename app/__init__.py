from flask import Flask, request
from .config import Config as cfg
from app.trello import trello_bp


def create_app():
    app = Flask(__name__)

    # index route
    @app.route("/")
    def index():
        return "Trello SharePoint Integration is running!"

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")

    return app
