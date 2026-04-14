"""
@milehigh-header
schema_version: 1
purpose: Flask app factory — registers all blueprints, starts APScheduler (queue drainer + heartbeat), and spawns the daemon outbox-retry thread.
exports:
  create_app: Factory that builds and returns the configured Flask application
  init_scheduler: Starts APScheduler with queue-drainer (5 min) and heartbeat (30 min) jobs
imports_from: [app/trello, app/procore, app/brain, app/auth/routes, app/history, app/admin, app/onedrive, app/models, app/config, app/db_config, app/logging_config, app/services/outbox_service, app/trello/api, apscheduler]
imported_by: [run.py]
invariants:
  - Scheduler only starts on one process: checks WERKZEUG_RUN_MAIN or IS_RENDER_SCHEDULER to avoid duplication in multi-worker deploys.
  - APScheduler uses a 3-worker thread pool; outbox retry runs on a separate daemon thread (2s idle / 0.5s active / 5s error sleep).
  - Blueprint registration order matters: API blueprints must register before the React catch-all route.
  - Application entry point via run.py or wsgi.py — not imported by other app modules.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
import os
import atexit
import time
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

# Blueprints
from app.trello import trello_bp
from app.procore import procore_bp
from app.brain import brain_bp
from app.auth.routes import auth_bp
from app.history import history_bp
from app.admin import admin_bp
from app.onedrive import onedrive_bp

from app.trello.api import create_trello_card_from_excel_data

# database imports
from app.models import db

from app.logging_config import configure_logging, get_logger

# Configure logging
logger = configure_logging(log_level="INFO", log_file="logs/app.log")


def init_scheduler(app):
    """Initialize the background scheduler for Trello queue draining and heartbeat."""
    from app.trello import drain_trello_queue

    # --- Prevent scheduler duplication in multi-worker environments ---
    # Only run the scheduler on one instance
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not os.environ.get(
        "IS_RENDER_SCHEDULER"
    ):
        logger.info("Skipping scheduler startup on this worker")
        return None

    # --- Configure scheduler ---
    executors = {
        "default": {
            "type": "threadpool",
            "max_workers": 3,
        }
    }
    scheduler = BackgroundScheduler(executors=executors)

    # OneDrive poll disabled — Brain job log is now the source of truth
    logger.info("OneDrive poll disabled — migrated to Brain job log as source of truth")

    # --- Queue drainer job (runs every 5 minutes) ---
    def queue_drainer():
        with app.app_context():
            try:
                drained = drain_trello_queue(max_items=5)
                if drained:
                    logger.info("Trello queue drainer executed", items_drained=drained)
            except Exception as e:
                logger.warning("Trello queue drainer failed", error=str(e))

    scheduler.add_job(
        func=queue_drainer,
        trigger="interval",
        minutes=5,
        id="trello_queue_drainer",
        name="Trello Queue Drainer",
        replace_existing=True,
    )

    # --- Optional heartbeat job to confirm scheduler alive ---
    scheduler.add_job(
        func=lambda: logger.info("Scheduler heartbeat: alive"),
        trigger="interval",
        minutes=30,
        id="heartbeat",
        replace_existing=True,
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))

    jobs_list = [
        {
            "id": "trello_queue_drainer",
            "name": "Trello Queue Drainer",
            "schedule": "Every 5 minutes",
            "description": "Drain queued Trello events (when lock is free)",
        },
        {
            "id": "heartbeat",
            "name": "Scheduler Heartbeat",
            "schedule": "Every 30 minutes",
            "description": "Confirms scheduler is alive",
        },
    ]

    # Log scheduler startup with all job details
    logger.info(
        "Scheduler jobs configured",
        jobs=jobs_list,
    )
    logger.info(
        "Scheduler configuration",
        is_render_scheduler=os.environ.get("IS_RENDER_SCHEDULER"),
        total_jobs=scheduler.get_jobs().__len__(),
        executor_type="ThreadPoolExecutor(max_workers=3)",
    )


def create_app():
    # Import config after dotenv is loaded
    from app.config import get_config
    from app.db_config import configure_database

    # Get the appropriate config class based on environment
    config_class = get_config()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure database separately
    configure_database(app)

    # Log the environment being used
    logger.info(f"Starting application in {config_class.ENV} environment")
    logger.info(
        f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')[:50]}..."
    )

    # Get allowed origins from environment variable
    allowed_origins = app.config.get("CORS_ORIGINS", "*")
    if allowed_origins != "*":
        # Parse comma-separated list if provided
        allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]

    # Enable CORS for React frontend
    # Use a simpler configuration that applies to all routes
    # This ensures CORS headers are always sent, even on errors
    CORS(
        app,
        resources={r"/*": {"origins": allowed_origins}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    )

    # Configure React frontend serving
    FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "dist"

    # List of API route prefixes to exclude from React catch-all
    API_ROUTE_PREFIXES = [
        "api/",
        "jobs/",
        "trello/",
        "procore/",
        "brain/",
        "admin/",
    ]

    def is_api_route(path):
        """Check if a path is an API route that should be handled by Flask."""
        if not path:
            return False
        # Note: /jobs is handled separately in the list_jobs route to distinguish
        # between API requests (JSON) and browser requests (React app)
        # Check if path starts with any API prefix
        return any(path.startswith(prefix) for prefix in API_ROUTE_PREFIXES)

    # Database is configured by configure_database() above
    # Initialize database
    db.init_app(app)

    # Initialize the database - only create tables, don't drop and reseed
    with app.app_context():
        # Only create tables if they don't exist
        db.create_all()

        # Start background thread for outbox retry processing
        # This handles retries for outbox items that failed immediate processing
        import threading
        import time
        from app.services.outbox_service import OutboxService

        def outbox_retry_worker():
            """Background thread that continuously processes pending outbox items for retries."""
            logger.info("Outbox retry worker thread started")
            while True:
                try:
                    with app.app_context():
                        # Process pending items that are ready for retry
                        processed = OutboxService.process_pending_items(limit=10)
                        if processed == 0:
                            # No items to process, wait a bit before checking again
                            time.sleep(2)
                        else:
                            # Processed some items, check again soon for more
                            time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Error in outbox retry worker: {e}", exc_info=True)
                    # Wait longer on error before retrying
                    time.sleep(5)

        # Start the background thread as a daemon (will stop when main process stops)
        outbox_thread = threading.Thread(
            target=outbox_retry_worker, daemon=True, name="outbox-retry-worker"
        )
        outbox_thread.start()
        logger.info("Outbox retry worker thread started successfully")

        # Initialize the scheduler for OneDrive polling
        init_scheduler(app)

        # # Check if we need to seed the database (only if empty)
        # from app.models import Job
        # job_count = Job.query.count()
        # if job_count == 0:
        #     print(f"No jobs found in database, seeding with fresh data...")
        #     combined_data = combine_trello_excel_data()
        #     seed_from_combined_data(combined_data)
        # else:
        #     print(f"Database already contains {job_count} jobs, skipping seed.")

    # Configure static file serving for React frontend
    # Get the path to the frontend build directory
    frontend_dist_path = os.path.join(
        Path(__file__).parent.parent,  # Go up from app/__init__.py to project root
        "frontend",
        "dist",
    )

    # Jobs route - display all jobs in database
    def determine_stage_from_db_fields(job):
        """
        Get the stage from the job's stage field.
        Returns the stage name or 'Released' if the stage field is None/empty.
        """
        # Use stage field directly from database
        if hasattr(job, "stage") and job.stage:
            return job.stage
        return "Released"

    # Index route - serve React app
    @app.route("/")
    def index():
        if FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / "index.html").exists():
            return send_file(FRONTEND_BUILD_DIR / "index.html")
        return (
            "Welcome to the Trello OneDrive Sync App! (React build not found. Run 'npm run build' in frontend directory.)",
            200,
        )

    # Job Log route - serve React app
    # DISABLED: Job log functionality not working yet
    @app.route("/job-log")
    def job_log():
        """Serve the React app for the Job Log page. Frontend will call /api/jobs for data."""
        if FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / "index.html").exists():
            return send_file(FRONTEND_BUILD_DIR / "index.html")
        return (
            "React build not found. Run 'npm run build' in the frontend directory.",
            200,
        )

    # Serve static assets from React build (JS, CSS, images, etc.)
    @app.route("/assets/<path:filename>")
    def serve_static_assets(filename):
        assets_dir = FRONTEND_BUILD_DIR / "assets"
        if assets_dir.exists():
            return send_from_directory(assets_dir, filename)
        return "Assets not found", 404

    # Serve root-level static files from dist directory
    # This handles favicon, robots.txt, and any other root-level static files
    @app.route("/favicon.ico")
    @app.route("/robots.txt")
    @app.route("/vite.svg")
    @app.route("/bananas-svgrepo-com.svg")
    def serve_root_static_files():
        filename = request.path.lstrip("/")
        file_path = FRONTEND_BUILD_DIR / filename

        # Special handling for favicon.ico - serve SVG if .ico doesn't exist
        if filename == "favicon.ico" and not file_path.exists():
            svg_path = FRONTEND_BUILD_DIR / "bananas-svgrepo-com.svg"
            if svg_path.exists():
                return send_file(svg_path, mimetype="image/svg+xml")

        if file_path.exists() and file_path.is_file():
            return send_file(file_path)
        from flask import abort

        abort(404)

    @app.route("/api/create_card", methods=["POST"])
    def new_card():
        data = request.get_json()

        # Create the card
        result = create_trello_card_from_excel_data(data, "Fit Up Complete.")

        if result["success"]:
            return (
                jsonify({"message": "Card created", "card_id": result["card_id"]}),
                200,
            )
        else:
            # Check if it's a duplicate job (409 Conflict) vs other errors (500)
            if "already exists in database" in result.get("error", ""):
                return (
                    jsonify(
                        {"message": "Card creation failed", "error": result["error"]}
                    ),
                    409,
                )
            else:
                return (
                    jsonify(
                        {"message": "Card creation failed", "error": result["error"]}
                    ),
                    500,
                )

    @app.route("/procore/add-link", methods=["POST", "GET"])
    def add_procore_link():
        """
        Add a Procore link to a Trello card for a given job and release.

        Query parameters:
            job (int): Job number (required)
            release (str): Release number (required)

        Returns:
            JSON response with success status and details
        """
        try:
            from app.procore.procore import add_procore_link_to_trello_card

            job = request.args.get("job", type=int)
            release = request.args.get("release", type=str)

            if not job or not release:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Missing required parameters",
                            "error": "Both 'job' (int) and 'release' (str) are required",
                        }
                    ),
                    400,
                )

            logger.info("Adding Procore link to Trello card", job=job, release=release)

            result = add_procore_link_to_trello_card(job, release)

            if result is None:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Failed to add Procore link",
                            "error": "Job not found, no Trello card, or no Procore submittal found",
                            "job": job,
                            "release": release,
                        }
                    ),
                    404,
                )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Procore link added to Trello card successfully",
                        "job": job,
                        "release": release,
                        "card_id": result.get("card_id"),
                        "viewer_url": result.get("viewer_url"),
                    }
                ),
                200,
            )

        except Exception as e:
            logger.error(
                "Error adding Procore link", error=str(e), job=job, release=release
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Error adding Procore link",
                        "error": str(e),
                        "job": job,
                        "release": release,
                    }
                ),
                500,
            )

    # Register blueprints before catch-all so API routes (e.g. POST /api/auth/login) are matched first
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(procore_bp, url_prefix="/procore")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")
    # app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(brain_bp, url_prefix="/brain")
    app.register_blueprint(auth_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Catch-all route for React Router (must be last, after all API routes)
    # This handles direct URL access to React routes like /history, /operations, etc.
    # Note: /jobs is handled above with special logic to distinguish API vs browser requests
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_react_app(path):
        # Skip if this is an API route
        if is_api_route(path):
            # Return 404 for API routes that don't exist
            from flask import abort

            abort(404)

        # Check if this is a static file in the dist directory (not in assets)
        # This handles any root-level static files we might have missed
        if path and not path.startswith("assets/"):
            static_file_path = FRONTEND_BUILD_DIR / path
            if static_file_path.exists() and static_file_path.is_file():
                return send_file(static_file_path)

        # Serve index.html for all React routes
        # React Router will handle client-side routing
        if FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / "index.html").exists():
            return send_file(FRONTEND_BUILD_DIR / "index.html")
        else:
            return (
                "React build not found. Run 'npm run build' in the frontend directory.",
                404,
            )

    # Global error handler to ensure CORS headers are always included
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle all exceptions and ensure CORS headers are included"""
        from flask_cors import cross_origin

        # Log the error
        logger.error("Unhandled exception", error=str(e), exc_info=True)

        # Return JSON error response with proper status code
        if hasattr(e, "code"):
            status_code = e.code
        elif hasattr(e, "status_code"):
            status_code = e.status_code
        else:
            status_code = 500

        response = jsonify(
            {"error": str(e), "message": "An error occurred processing your request"}
        )
        response.status_code = status_code

        # CORS headers should be added automatically by Flask-CORS
        # but we ensure they're present
        return response

    return app
