from flask import Flask
from app.trello import trello_bp
from app.onedrive import onedrive_bp

# database imports
from app.models import db
from app.seed import seed_from_combined_data
from app.combine import combine_trello_excel_data

# scheduler imports
from apscheduler.schedulers.background import BackgroundScheduler
import logging

logger = logging.getLogger(__name__)


def init_scheduler(app):
    """
    Initialize the scheduler to run the OneDrive poll every 2 minutes.
    Now with lock-aware scheduling.
    """
    # Import here to avoid circular imports
    from app.onedrive.utils import run_onedrive_poll
    from app.sync_lock import sync_lock_manager

    scheduler = BackgroundScheduler()

    def scheduled_run():
        """
        Wrapper that handles locking gracefully
        """
        with app.app_context():
            # Check if sync is already running before attempting
            if sync_lock_manager.is_locked():
                current_op = sync_lock_manager.get_current_operation()
                logger.info(
                    f"Skipping scheduled OneDrive poll - sync locked by: {current_op}"
                )
                return  # Just skip this run, try again in 2 minutes

            try:
                logger.info("Starting scheduled OneDrive poll")
                run_onedrive_poll()  # This will now acquire the lock automatically
                logger.info("Scheduled OneDrive poll completed successfully")

            except RuntimeError as e:
                # This catches lock acquisition failures
                logger.info(f"Scheduled OneDrive poll skipped due to lock: {e}")
                # This is normal - just means something else is running

            except Exception as e:
                # This catches actual errors in the sync process
                logger.error(f"Scheduled OneDrive poll failed with error: {e}")
                # You might want to add error reporting/alerting here

    scheduler.add_job(
        func=scheduled_run,
        trigger="interval",
        minutes=2,
        id="onedrive_poll",  # Give it an ID for monitoring
        name="OneDrive Polling Job",
    )

    scheduler.start()
    logger.info("OneDrive polling scheduler started (every 2 minutes)")

    return scheduler  # Return scheduler in case you want to control it later


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.sqlite"
    db.init_app(app)

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

    # Add a status route for monitoring
    @app.route("/sync/status")
    def sync_status():
        from app.sync_lock import sync_lock_manager
        from flask import jsonify

        try:
            status = sync_lock_manager.get_status()
            return jsonify(status), 200
        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return (
                jsonify(
                    {"status": "error", "message": f"Could not get status: {str(e)}"}
                ),
                500,
            )

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    # Start the scheduler AFTER everything else is set up
    init_scheduler(app)  # start the poller

    return app
