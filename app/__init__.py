from flask import Flask, request, make_response
from .config import Config as cfg
from app.trello import trello_bp


def create_app():
    app = Flask(__name__)

    # index route
    @app.route("/")
    def index():
        validation_token = request.args.get("validationToken")

        if validation_token:
            resp = make_response(validation_token, 200)
            resp.headers["Content-Type"] = "text/plain"
            return resp
        # Process actual notifications here
        return "", 202

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")

    return app
