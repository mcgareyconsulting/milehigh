from flask import Flask, request, make_response
from .config import Config as cfg
from app.trello import trello_bp
from app.onedrive import onedrive_bp
from app.onedrive.api import get_excel_dataframe

# database imports
from app.models import db
from app.seed import seed_job_releases_from_df
import pandas as pd


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.sqlite"
    db.init_app(app)

    # Initialize the database
    with app.app_context():
        df = get_excel_dataframe()  # or create DataFrame from your source
        db.create_all()
        seed_job_releases_from_df(df)

    # index route
    @app.route("/")
    def index():
        return "Welcome to the Trello OneDrive Sync App!"

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    return app
