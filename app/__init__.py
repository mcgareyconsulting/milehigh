"""
@milehigh-header
schema_version: 1
purpose: Flask app factory — registers all blueprints, starts APScheduler (queue drainer + heartbeat), and spawns the daemon outbox-retry thread.
exports:
  create_app: Factory that builds and returns the configured Flask application
  init_scheduler: Starts APScheduler with queue-drainer (5 min) and heartbeat (30 min) jobs
imports_from: [app/trello, app/procore, app/brain, app/auth/routes, app/history, app/admin, app/models, app/config, app/db_config, app/logging_config, app/services/outbox_service, app/trello/api, apscheduler]
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
from app.api import api_bp
from app.lake import lake_bp

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

    # --- Nightly FC PDF Pack retry worker (2:00 AM Mountain Time) ---
    # Procore's Final PDF Pack can land up to ~24h after a release hits the
    # job log; this catches the misses by retrying releases with NULL
    # viewer_url that were released within the last 7 days.
    # Pinned to America/Denver so the fire time tracks MT through DST,
    # independent of the Render container's UTC clock.
    def fc_pdf_retry():
        from app.procore.fc_retry_worker import retry_missing_fc_viewer_urls
        with app.app_context():
            try:
                retry_missing_fc_viewer_urls(trigger="cron")
            except Exception as e:
                logger.error("FC PDF retry job failed", error=str(e), exc_info=True)

    scheduler.add_job(
        func=fc_pdf_retry,
        trigger="cron",
        hour=2,
        minute=0,
        timezone="America/Denver",
        id="fc_pdf_retry",
        name="FC PDF Pack Retry",
        replace_existing=True,
    )

    # --- Banana Boy mailbox poll (bb@mhmw.com → data lake bronze) ---
    # Incrementally pulls forwarded emails into RawSourceRecord. Gated by
    # BB_MAIL_INGEST_ENABLED so it stays dormant until the Azure app-only
    # access policy is in place. On-demand pulls go through /lake/ingest/mail/pull.
    bb_mail_poll_minutes = app.config.get("BB_MAIL_POLL_MINUTES", 15)

    def bb_mail_poll():
        with app.app_context():
            if not app.config.get("BB_MAIL_INGEST_ENABLED"):
                return
            from app.lake.ingest import m365_mail
            try:
                result = m365_mail.poll()
                if result.get("created") or result.get("updated"):
                    logger.info("BB mail poll landed records", **{
                        k: result[k] for k in ("mailboxes", "created", "updated", "unchanged", "fetched")
                    })
                # Consume newly-landed emails into supplier material orders (no-op
                # for non-order mail; idempotent so a stable mailbox is cheap).
                try:
                    from app.brain.material_orders import service as material_orders_service
                    material_orders_service.ingest_unprocessed()
                except Exception as e:
                    logger.error("Material order ingest failed", error=str(e), exc_info=True)
            except Exception as e:
                logger.error("BB mail poll failed", error=str(e), exc_info=True)

    scheduler.add_job(
        func=bb_mail_poll,
        trigger="interval",
        minutes=bb_mail_poll_minutes,
        id="bb_mail_poll",
        name="BB Mailbox Poll",
        replace_existing=True,
    )

    # Surface the BB ingest gate at startup so it's obvious whether forwarded
    # mail will actually be pulled. Logs on every boot regardless of the flag.
    # Tenant + client id are common to both the app-only and device-code flows;
    # the device-code (public client) path has no secret, so we don't require one.
    _bb_enabled = bool(app.config.get("BB_MAIL_INGEST_ENABLED"))
    _bb_has_app_reg = bool(
        app.config.get("AZURE_TENANT_ID") and app.config.get("AZURE_CLIENT_ID")
    )
    logger.info(
        "BB mail ingest status",
        enabled=_bb_enabled,
        mailbox=app.config.get("BB_MAILBOX"),
        poll_minutes=bb_mail_poll_minutes,
        azure_app_registered=_bb_has_app_reg,
        note=(
            "active — polling on schedule" if _bb_enabled and _bb_has_app_reg
            else "DORMANT — set BB_MAIL_INGEST_ENABLED=1"
            + ("" if _bb_has_app_reg else " and AZURE_TENANT_ID / AZURE_CLIENT_ID")
        ),
    )

    # --- Checklist deadline notifications (daily 6:00 AM Mountain Time) ---
    # Pings the owner of each accepted post-meeting to-do whose due date is near
    # or overdue (deduped via ChecklistItem.last_notified_at).
    def checklist_due_scan():
        from app.brain.meetings.service import notify_due_items
        with app.app_context():
            try:
                notify_due_items()
            except Exception as e:
                logger.error("Checklist due scan failed", error=str(e), exc_info=True)

    scheduler.add_job(
        func=checklist_due_scan,
        trigger="cron",
        hour=6,
        minute=0,
        timezone="America/Denver",
        id="checklist_due_scan",
        name="Checklist Deadline Notifications",
        replace_existing=True,
    )

    # --- Calendar → Recall scheduling (every RECALL_CALENDAR_POLL_MINUTES) ---
    # Scans the configured mailbox's calendar for upcoming Teams meetings and
    # schedules a Recall bot to join each at its start time. Gated by
    # RECALL_CALENDAR_ENABLED so it stays dormant until the app-only Calendars.Read
    # access policy is in place.
    calendar_recall_poll_minutes = app.config.get("RECALL_CALENDAR_POLL_MINUTES", 10)

    def calendar_recall_poll():
        with app.app_context():
            if not app.config.get("RECALL_CALENDAR_ENABLED"):
                return
            from app.brain.meetings import calendar
            try:
                result = calendar.poll()
                if result.get("scheduled"):
                    logger.info("Calendar→Recall scheduled bots", **result)
            except Exception as e:
                logger.error("Calendar→Recall poll failed", error=str(e), exc_info=True)

    scheduler.add_job(
        func=calendar_recall_poll,
        trigger="interval",
        minutes=calendar_recall_poll_minutes,
        id="calendar_recall_poll",
        name="Calendar → Recall Scheduler",
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
        {
            "id": "fc_pdf_retry",
            "name": "FC PDF Pack Retry",
            "schedule": "Daily at 02:00 America/Denver",
            "description": "Retry Procore FC viewer_url for releases missing it (last 7 days)",
        },
        {
            "id": "bb_mail_poll",
            "name": "BB Mailbox Poll",
            "schedule": f"Every {bb_mail_poll_minutes} minutes",
            "description": "Pull forwarded emails from bb@mhmw.com into the data lake (when enabled)",
        },
        {
            "id": "checklist_due_scan",
            "name": "Checklist Deadline Notifications",
            "schedule": "Daily at 06:00 America/Denver",
            "description": "Notify owners of accepted post-meeting to-dos that are due soon/overdue",
        },
        {
            "id": "calendar_recall_poll",
            "name": "Calendar → Recall Scheduler",
            "schedule": f"Every {calendar_recall_poll_minutes} minutes",
            "description": "Schedule Recall bots for upcoming Teams meetings on the BB calendar (when enabled)",
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

    # Cap multipart upload body size — used by the PDF markup endpoints. Flask
    # turns oversize requests into a 413 automatically.
    app.config.setdefault('MAX_CONTENT_LENGTH', 50 * 1024 * 1024)

    # Configure database separately
    configure_database(app)

    # Log the environment being used
    logger.info(f"Starting application in {config_class.ENV} environment")
    logger.info(
        f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')[:50]}..."
    )
    if app.config.get("TRELLO_MOCK"):
        logger.info("TRELLO_MOCK enabled — outbound move_card calls will be simulated and inbound webhooks dropped")

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

    @app.after_request
    def apply_cache_headers(response):
        # The HTML shell must revalidate every load — without this, a tab cached pre-deploy
        # rides forever on stale bundle hashes (Render purges old chunks on each deploy).
        path = request.path or ""
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        return response

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
        "lake/",
    ]

    # Paths under an API prefix that are actually React pages and should
    # fall through to the SPA. The admin blueprint owns most of /admin/*,
    # but a handful of routes are React-rendered admin pages registered
    # in frontend/src/App.jsx.
    SPA_PATHS_UNDER_API_PREFIX = {
        "admin/fc-collection",
    }

    def is_api_route(path):
        """Check if a path is an API route that should be handled by Flask."""
        if not path:
            return False
        if path in SPA_PATHS_UNDER_API_PREFIX:
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

        from app.procore.reconcile import ProcoreReconcileService

        def outbox_retry_worker():
            """Background thread that continuously processes pending outbox items for retries."""
            logger.info("Outbox retry worker thread started")
            while True:
                try:
                    with app.app_context():
                        # Process pending items that are ready for retry
                        processed = OutboxService.process_pending_items(limit=10)
                        # Process due Procore submittal reconciles (delayed re-fetch safety net)
                        reconciled = ProcoreReconcileService.process_due(limit=10)
                        if processed + reconciled == 0:
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

        # Initialize the scheduler for Trello queue drainer + heartbeat
        init_scheduler(app)

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
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(brain_bp, url_prefix="/brain")
    app.register_blueprint(auth_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(lake_bp, url_prefix="/lake")

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
