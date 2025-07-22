from flask import Flask, request, make_response
from .config import Config as cfg
from app.trello import trello_bp
from app.onedrive import onedrive_bp


def create_app():
    app = Flask(__name__)

    # index route
    @app.route("/")
    def index():
        return "Welcome to the Trello OneDrive Sync App!"

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    return app
