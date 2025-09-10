from flask import Flask, request, make_response, jsonify
from .config import Config as cfg
from app.trello import trello_bp
from app.onedrive import onedrive_bp
from app.onedrive.api import get_excel_dataframe
from app.combine import combine_trello_excel_data

# database imports
from app.models import db, query_job_releases, Job
from app.seed import seed_from_combined_data
import pandas as pd

# scheduler imports
from apscheduler.schedulers.background import BackgroundScheduler
from app.onedrive.utils import run_onedrive_poll


def init_scheduler(app):
    scheduler = BackgroundScheduler()

    def scheduled_run():
        with app.app_context():
            run_onedrive_poll()  # now has access to Flask app & db

    scheduler.add_job(func=scheduled_run, trigger="interval", minutes=2)
    scheduler.start()


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.sqlite"
    db.init_app(app)
    init_scheduler(app)  # start the poller

    # Initialize the database
    # with app.app_context():
    #     db.drop_all()
    #     db.create_all()
    #     combined_data = combine_trello_excel_data()
    #     seed_from_combined_data(combined_data)

    # index route
    @app.route("/")
    def index():
        return "Welcome to the Trello OneDrive Sync App!"

    # @app.route("/compare", methods=["GET"])
    # def compare():
    #     from app.sync import run_comparison

    #     differences = run_comparison()
    #     return jsonify(differences)

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    return app
