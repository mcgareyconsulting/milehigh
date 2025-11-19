import os
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from app.trello import trello_bp
from app.onedrive import onedrive_bp
from app.procore import procore_bp
from app.trello.api import create_trello_card_from_excel_data

# database imports
from app.models import db, SyncOperation, SyncLog, SyncStatus
from app.seed import seed_from_combined_data, incremental_seed_missing_jobs, get_trello_excel_cross_check_summary
from app.combine import combine_trello_excel_data

# scheduler imports
from apscheduler.schedulers.background import BackgroundScheduler
from app.logging_config import configure_logging, get_logger
from datetime import datetime, timedelta
from sqlalchemy import func

# Configure logging
logger = configure_logging(log_level="INFO", log_file="logs/app.log")

# Import datetime utilities
from app.datetime_utils import format_datetime_mountain


def get_socketio_cors_origins():
    """Get allowed CORS origins for SocketIO from environment or default to localhost:5173 (Vite default)"""
    allowed_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    if allowed_origins != "*":
        # Parse comma-separated list if provided
        origins = [origin.strip() for origin in allowed_origins.split(",")]
        return origins
    # If "*" is explicitly set, allow all (not recommended for production)
    return "*"

# Initialize SocketIO with CORS restricted to frontend origins
# Use eventlet for async websocket support with Gunicorn
# Falls back to threading if eventlet is not available
try:
    import eventlet
    async_mode = 'eventlet'
except ImportError:
    async_mode = 'threading'

socketio = SocketIO(
    cors_allowed_origins=get_socketio_cors_origins(),
    async_mode=async_mode,
    logger=False,
    engineio_logger=False
)

import time
import atexit
from apscheduler.executors.pool import ThreadPoolExecutor

def init_scheduler(app):
    """Initialize the scheduler to run the OneDrive poll every hour."""
    from app.onedrive.utils import run_onedrive_poll
    from app.sync_lock import sync_lock_manager
    from app.trello import drain_trello_queue

    # --- Prevent scheduler duplication in multi-worker environments ---
    # Only run the scheduler on one instance
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not os.environ.get("IS_RENDER_SCHEDULER"):
        logger.info("Skipping scheduler startup on this worker")
        return None

    # --- Configure scheduler ---
    executors = {"default": ThreadPoolExecutor(3)}
    scheduler = BackgroundScheduler(executors=executors)

    # --- Simple retry wrapper for transient errors ---
    def retry_with_backoff(func, retries=3, base_delay=5):
        for i in range(retries):
            try:
                return func()
            except Exception as e:
                if i == retries - 1:
                    raise
                delay = base_delay * (2 ** i)
                logger.warning(
                    "Retrying OneDrive poll after failure",
                    attempt=i + 1,
                    delay=delay,
                    error=str(e)
                )
                time.sleep(delay)

    # --- The actual scheduled task ---
    def scheduled_run():
        with app.app_context():
            if sync_lock_manager.is_locked():
                current_op = sync_lock_manager.get_current_operation()
                logger.info("Skipping scheduled OneDrive poll - sync locked", current_operation=current_op)

                try:
                    drained = drain_trello_queue(max_items=3)
                    if drained:
                        logger.info("Drained Trello queue while OneDrive locked", drained=drained)
                except Exception as e:
                    logger.warning("Trello queue drain failed during skip", error=str(e))
                return

            try:
                logger.info("Starting scheduled OneDrive poll")

                # Pre-drain Trello queue
                try:
                    drained_pre = drain_trello_queue(max_items=2)
                    if drained_pre:
                        logger.info("Pre-drain Trello queue", drained=drained_pre)
                except Exception:
                    pass

                # Run OneDrive poll with retry logic
                retry_with_backoff(run_onedrive_poll)

                # Post-drain Trello queue
                try:
                    drained_post = drain_trello_queue(max_items=5)
                    if drained_post:
                        logger.info("Post-drain Trello queue", drained=drained_post)
                except Exception:
                    pass

                logger.info("Scheduled OneDrive poll completed successfully")

            except RuntimeError as e:
                logger.info("Scheduled OneDrive poll skipped due to runtime lock", error=str(e))
            except Exception as e:
                logger.error("Scheduled OneDrive poll failed", error=str(e))

    # --- Add the main job (runs hourly on the hour) ---
    scheduler.add_job(
        func=scheduled_run,
        trigger="cron",
        minute="0",
        hour="*",
        id="onedrive_poll",
        name="OneDrive Polling Job",
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

    logger.info("OneDrive polling scheduler started", schedule="every hour on the hour")
    return scheduler


def create_app():
    app = Flask(__name__)

   # Get allowed origins from environment variable
    allowed_origins = os.environ.get("CORS_ORIGINS", "*")
    if allowed_origins != "*":
        # Parse comma-separated list if provided
        allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]
    
    # Enable CORS for React frontend
    CORS(app, resources={
        r"/api/*": {"origins": allowed_origins},
        r"/sync/*": {"origins": allowed_origins},
        r"/jobs/*": {"origins": allowed_origins},
        r"/jobs/history": {"origins": allowed_origins},
        r"/snapshot/*": {"origins": allowed_origins},
        r"/snapshots/*": {"origins": allowed_origins},
        r"/procore/*": {"origins": allowed_origins},
        r"/files/*": {"origins": allowed_origins},
    })
    
    # Initialize SocketIO with app
    socketio.init_app(app)
    
    # Database configuration - use environment variable for production
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # For production databases (PostgreSQL, MySQL, etc.)
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,        # Detect and refresh dead connections before use
            "pool_recycle": 280,          # Recycle connections slightly before Render's idle timeout (~5 min)
            "pool_size": 5,               # Render free-tier DBs are resource-constrained; keep this modest
            "max_overflow": 10,           # Allow some burst usage during concurrent jobs
            "pool_timeout": 30,           # Wait up to 30s for a connection before raising
            "connect_args": {
                "sslmode": "require",     # Enforce SSL
                "connect_timeout": 10,    # Fail fast if DB can’t be reached
                "application_name": "trello_sharepoint_app",
                "options": "-c statement_timeout=30000"  # 30s max per SQL statement
            },
        }

    else:
        # Fallback to SQLite for local development
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.sqlite"
    
    db.init_app(app)

    # Initialize the database - only create tables, don't drop and reseed
    with app.app_context():
        # Only create tables if they don't exist
        db.create_all()
        
        # Check if we need to seed the database (only if empty)
        from app.models import Job
        job_count = Job.query.count()
        if job_count == 0:
            print(f"No jobs found in database, seeding with fresh data...")
            combined_data = combine_trello_excel_data()
            seed_from_combined_data(combined_data)
        else:
            print(f"Database already contains {job_count} jobs, skipping seed.")

    # Index route
    @app.route("/")
    def index():
        return "Welcome to the Trello OneDrive Sync App!"

    # Jobs route - display all jobs in database
    @app.route("/jobs")
    def list_jobs():
        from app.models import Job
        try:
            jobs = Job.query.all()
            job_list = []
            for job in jobs:
                job_data = {
                    'id': job.id,
                    'job': job.job,
                    'release': job.release,
                    'job_name': job.job_name,
                    'description': job.description,
                    'pm': job.pm,
                    'by': job.by,
                    'released': format_datetime_mountain(job.released),
                    'fab_hrs': job.fab_hrs,
                    'install_hrs': job.install_hrs,
                    'paint_color': job.paint_color,
                    'trello_card_name': job.trello_card_name,
                    'trello_list_name': job.trello_list_name,
                    'last_updated_at': format_datetime_mountain(job.last_updated_at),
                    'source_of_update': job.source_of_update
                }
                job_list.append(job_data)
            
            return jsonify({
                'total_jobs': len(job_list),
                'jobs': job_list
            }), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route("/shipping/audit", methods=["GET", "POST"])
    def shipping_audit():
        """
        Run the shipping reconciliation scan and return the summary payload.
        """
        from app.scripts.check_shipping_lists import run_reconciliation

        try:
            summary = run_reconciliation()
            response_data = {"success": True}
            response_data.update(summary)
            return jsonify(response_data), 200
        except Exception as exc:
            logger.exception("Shipping audit failed")
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/shipping/enforce-excel", methods=["GET", "POST"])
    def shipping_enforce_excel():
        """
        Synchronize Excel staging columns for jobs in shipping lists.
        DB records remain unchanged; only Excel cells are updated.
        """
        from app.scripts.enforce_shipping_excel import enforce_shipping_excel

        dry_run = False
        batch_size = None
        include_details = False
        payload = request.get_json(silent=True) or {}

        if "dry_run" in payload:
            dry_run = bool(payload["dry_run"])
        else:
            dry_run_param = request.args.get("dry_run")
            if isinstance(dry_run_param, str):
                dry_run = dry_run_param.lower() in ("1", "true", "yes", "on")

        if "batch_size" in payload:
            try:
                batch_size_val = int(payload["batch_size"])
                if batch_size_val > 0:
                    batch_size = batch_size_val
            except (TypeError, ValueError):
                pass
        else:
            batch_size_param = request.args.get("batch_size")
            if batch_size_param is not None:
                try:
                    batch_size_val = int(batch_size_param)
                    if batch_size_val > 0:
                        batch_size = batch_size_val
                except (TypeError, ValueError):
                    pass

        if "include_details" in payload:
            include_details = bool(payload["include_details"])
        else:
            include_details_param = request.args.get("include_details")
            if isinstance(include_details_param, str):
                include_details = include_details_param.lower() in ("1", "true", "yes", "on")

        try:
            summary = enforce_shipping_excel(
                dry_run=dry_run,
                update_db=False,
                batch_size=batch_size,
                include_details=include_details,
            )
            response_data = {"success": True}
            response_data.update(summary)
            return jsonify(response_data), 200
        except Exception as exc:
            logger.exception("Shipping Excel enforcement failed")
            return jsonify({"success": False, "error": str(exc)}), 500

    # Job change history route
    @app.route("/jobs/<int:job>/<release>/history")
    def job_change_history_path(job, release):
        """Get change history for a specific job-release combination via URL path."""
        return _get_job_change_history(job, release)
    
    @app.route("/jobs/history")
    def job_change_history_query():
        """Get change history via query parameters.
        
        Query parameters:
            job (int): Job number (optional) - if provided, filters by job number
            release (str): Release number (optional) - if provided, filters by release
        
        Search scenarios:
            - Both provided: Returns history for specific job-release combination
            - Job only: Returns history for all releases of that job number
            - Release only: Returns history for all jobs with that release
            - Neither: Returns error (at least one required)
        
        Returns:
            JSON object with history array and search metadata
        """
        job = request.args.get('job', type=int)
        release = request.args.get('release', type=str)
        return _get_job_change_history(job, release)
    
    def _get_job_change_history(job, release):
        """Internal function to retrieve job change history."""
        from app.models import JobChangeLog, Job
        
        # At least one parameter must be provided
        if job is None and release is None:
            return jsonify({
                'error': 'Missing required parameters',
                'message': 'At least one of job (int) or release (str) is required',
                'usage': {
                    'job_only': '/jobs/history?job=<int>',
                    'release_only': '/jobs/history?release=<str>',
                    'both': '/jobs/history?job=<int>&release=<str>',
                    'path': '/jobs/<job>/<release>/history'
                }
            }), 400
        
        try:
            # Build change log query based on provided parameters
            log_query = JobChangeLog.query
            
            if job is not None:
                log_query = log_query.filter_by(job=job)
            if release is not None:
                log_query = log_query.filter_by(release=str(release))
            
            # Order by most recent first
            change_logs = log_query.order_by(JobChangeLog.changed_at.desc()).all()
            
            # Build job query to retrieve metadata for associated job-release combos
            job_query = Job.query
            if job is not None:
                job_query = job_query.filter_by(job=job)
            if release is not None:
                job_query = job_query.filter_by(release=str(release))
            job_records = job_query.all()
            
            # Format the response
            history = []
            job_releases = set()  # Track unique job-release combinations
            job_details = []
            
            for log in change_logs:
                history.append({
                    'id': log.id,
                    'job': log.job,
                    'release': log.release,
                    'change_type': log.change_type,
                    'field_name': log.field_name,
                    'from_value': log.from_value,
                    'to_value': log.to_value,
                    'changed_at': format_datetime_mountain(log.changed_at),
                    'source': log.source,
                    'operation_id': log.operation_id,
                    'triggered_by': log.triggered_by
                })
                job_releases.add((log.job, log.release))
            
            # Collect job metadata for frontend display
            for job_row in job_records:
                job_key = (job_row.job, job_row.release)
                job_releases.add(job_key)
                job_details.append({
                    'job': job_row.job,
                    'release': job_row.release,
                    'job_name': job_row.job_name,
                    'description': job_row.description,
                    'install_hrs': job_row.install_hrs,
                    'start_install': job_row.start_install.isoformat() if job_row.start_install else None,
                    'trello_list_name': job_row.trello_list_name,
                    'viewer_url': job_row.viewer_url
                })
            
            # If we have no job releases from change logs, ensure we include jobs that match the query
            if not job_releases and job_records:
                job_releases = {(jr.job, jr.release) for jr in job_records}
            
            # Determine search type for frontend
            search_type = 'both' if job is not None and release is not None else ('job' if job is not None else 'release')
            
            # Determine default selection for frontend convenience
            default_selection = None
            if job_details:
                # Try to match an exact job-release when both provided
                if job is not None and release is not None:
                    default_selection = next(
                        (detail for detail in job_details if detail['job'] == job and detail['release'] == str(release)),
                        None
                    )
                # Fallback to the first job detail if no exact match found
                if default_selection is None:
                    default_selection = job_details[0]
            
            return jsonify({
                'search_type': search_type,
                'search_job': job,
                'search_release': release,
                'job_releases': [{'job': jr[0], 'release': jr[1]} for jr in sorted(job_releases)],
                'total_changes': len(history),
                'history': history,
                'job_details': job_details,
                'default_selection': default_selection
            }), 200
            
        except Exception as e:
            logger.error("Error getting job change history", error=str(e), job=job, release=release)
            return jsonify({
                'error': 'Failed to retrieve change history',
                'message': str(e)
            }), 500

    # Sync status route
    @app.route("/sync/status")
    def sync_status():
        from app.sync_lock import sync_lock_manager
        try:
            status = sync_lock_manager.get_status()
            return jsonify(status), 200
        except Exception as e:
            logger.error("Error getting sync status", error=str(e))
            return jsonify({"status": "error", "message": f"Could not get status: {str(e)}"}), 500

    # Sync operations digest
    @app.route("/sync/operations")
    def sync_operations():
        """Get sync operations filtered by date range only (start/end)."""
        try:
            # Query parameters
            limit = request.args.get('limit', 50, type=int)
            start_date = request.args.get('start')  # YYYY-MM-DD
            end_date = request.args.get('end')      # YYYY-MM-DD

            query = SyncOperation.query

            # Apply date range on started_at (inclusive)
            if start_date:
                start_dt = datetime.fromisoformat(start_date + "T00:00:00")
                query = query.filter(SyncOperation.started_at >= start_dt)
            if end_date:
                end_dt = datetime.fromisoformat(end_date + "T23:59:59.999999")
                query = query.filter(SyncOperation.started_at <= end_dt)

            operations = query.order_by(SyncOperation.started_at.desc()).limit(limit).all()

            return jsonify({
                'operations': [op.to_dict() for op in operations],
                'total': len(operations),
                'filters': {
                    'limit': limit,
                    'start': start_date,
                    'end': end_date,
                }
            }), 200
        except Exception as e:
            logger.error("Error getting sync operations", error=str(e))
            return jsonify({"error": str(e)}), 500

    # Sync logs for a specific operation
    @app.route("/sync/operations/<operation_id>/logs")
    def sync_operation_logs(operation_id):
        """Get detailed logs for a specific sync operation."""
        try:
            logs = SyncLog.query.filter_by(operation_id=operation_id)\
                              .order_by(SyncLog.timestamp.asc()).all()
            
            return jsonify({
                'operation_id': operation_id,
                'logs': [{
                    'timestamp': format_datetime_mountain(log.timestamp),
                    'level': log.level,
                    'message': log.message,
                    'data': log.data
                } for log in logs]
            }), 200
            
        except Exception as e:
            logger.error("Error getting sync operation logs", operation_id=operation_id, error=str(e))
            return jsonify({"error": str(e)}), 500

    # Sync statistics
    @app.route("/sync/stats")
    def sync_stats():
        """Get sync statistics and health metrics."""
        from app.sync_lock import sync_lock_manager
        try:
            # Recent operations count by status
            recent_ops = SyncOperation.query.filter(
                SyncOperation.started_at >= datetime.utcnow() - timedelta(hours=24)
            ).all()
            
            status_counts = {}
            for op in recent_ops:
                status_counts[op.status.value] = status_counts.get(op.status.value, 0) + 1
            
            # Success rate
            total_ops = len(recent_ops)
            successful_ops = len([op for op in recent_ops if op.status == SyncStatus.COMPLETED])
            success_rate = (successful_ops / total_ops * 100) if total_ops > 0 else 0
            
            # Average duration
            completed_ops = [op for op in recent_ops if op.duration_seconds is not None]
            avg_duration = sum(op.duration_seconds for op in completed_ops) / len(completed_ops) if completed_ops else 0
            
            return jsonify({
                'last_24_hours': {
                    'total_operations': total_ops,
                    'status_breakdown': status_counts,
                    'success_rate_percent': round(success_rate, 2),
                    'average_duration_seconds': round(avg_duration, 2)
                },
                'current_status': {
                    'sync_locked': sync_lock_manager.is_locked(),
                    'current_operation': sync_lock_manager.get_current_operation()
                }
            }), 200
            
        except Exception as e:
            logger.error("Error getting sync stats", error=str(e))
            return jsonify({"error": str(e)}), 500


    # Lightweight HTML dashboard for operations and logs
    @app.route('/sync/operations/view')
    def sync_operations_view():
        try:
            limit = request.args.get('limit', 50, type=int)
            selected_date = request.args.get('date')  # YYYY-MM-DD

            # Build list of distinct operation dates (YYYY-MM-DD), newest first
            date_rows = (
                db.session.query(func.date(SyncOperation.started_at))
                .distinct()
                .order_by(func.date(SyncOperation.started_at).desc())
                .all()
            )
            available_dates = [str(r[0]) for r in date_rows if r[0] is not None]
            # Default to most recent available date if none selected
            if not selected_date and available_dates:
                selected_date = available_dates[0]

            # Reuse the JSON endpoint logic by calling it internally
            with app.test_request_context(
                f"/sync/operations?limit={limit}"
                + (f"&start={selected_date}&end={selected_date}" if selected_date else "")
            ):
                resp, code = sync_operations()
            data = resp.get_json()

            from flask import render_template_string
            html = render_template_string(
                """
                <html>
                  <head>
                    <title>Sync Operations</title>
                    <style>
                      body { font-family: Arial, sans-serif; margin: 16px; }
                      table { border-collapse: collapse; width: 100%; }
                      th, td { border: 1px solid #ddd; padding: 8px; }
                      th { background: #f4f4f4; text-align: left; }
                      .filters { margin-bottom: 12px; }
                      .muted { color: #666; font-size: 12px; }
                    </style>
                  </head>
                  <body>
                    <h2>Sync Operations</h2>
                    <form class=\"filters\" method=\"get\"> 
                      <label>Date: 
                        <select name=\"date\"> 
                          {% for d in available_dates %}
                            <option value=\"{{ d }}\" {% if selected_date==d %}selected{% endif %}>{{ d }}</option>
                          {% endfor %}
                        </select>
                      </label>
                      <input type=\"number\" name=\"limit\" min=\"1\" max=\"200\" value=\"{{ limit }}\" />
                      <button type=\"submit\">Apply</button>
                      <a href=\"/sync/operations/view\">Reset</a>
                    </form>
                    <table>
                      <thead>
                        <tr>
                          <th>Started</th>
                          <th>Operation ID</th>
                          <th>Type</th>
                          <th>Status</th>
                          <th>Source</th>
                          <th>Duration (s)</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {% for op in data.operations %}
                          <tr>
                            <td>{{ op.started_at }}</td>
                            <td>{{ op.operation_id }}</td>
                            <td>{{ op.operation_type }}</td>
                            <td>{{ op.status }}</td>
                            <td class=\"muted\">{{ op.source_system }} {{ op.source_id or '' }}</td>
                            <td>{{ '%.2f'|format(op.duration_seconds or 0) }}</td>
                            <td><a href=\"/sync/operations/{{ op.operation_id }}/logs/view\">logs</a></td>
                          </tr>
                        {% endfor %}
                      </tbody>
                    </table>
                    <p class=\"muted\">Total: {{ data.total }}</p>
                  </body>
                </html>
                """,
                data=data,
                available_dates=available_dates,
                selected_date=selected_date,
                limit=limit,
            )
            return html
        except Exception as e:
            logger.error("Error rendering operations view", error=str(e))
            return "Error", 500

    @app.route('/sync/operations/<operation_id>/logs/view')
    def sync_operation_logs_view(operation_id):
        try:
            # Fetch logs using existing JSON endpoint
            logs_resp, code = sync_operation_logs(operation_id)
            data = logs_resp.get_json()
            from flask import render_template_string
            html = render_template_string(
                """
                <html>
                  <head>
                    <title>Logs - {{ operation_id }}</title>
                    <style>
                      body { font-family: Arial, sans-serif; margin: 16px; }
                      pre { white-space: pre-wrap; word-wrap: break-word; }
                      .muted { color: #666; font-size: 12px; }
                      .log { border-bottom: 1px solid #eee; padding: 6px 0; }
                    </style>
                  </head>
                  <body>
                    <h3>Logs for operation {{ operation_id }}</h3>
                    <p class="muted"><a href="/sync/operations/view">Back to operations</a></p>
                    {% for log in data.logs %}
                      <div class="log">
                        <div class="muted">{{ log.timestamp }} - {{ log.level }}</div>
                        <div><strong>{{ log.message }}</strong></div>
                        {% if log.data %}
                          <pre>{{ log.data | tojson(indent=2) }}</pre>
                        {% endif %}
                      </div>
                    {% endfor %}
                  </body>
                </html>
                """,
                operation_id=operation_id,
                data=data,
            )
            return html
        except Exception as e:
            logger.error("Error rendering logs view", operation_id=operation_id, error=str(e))
            return "Error", 500

    @app.route("/api/create_card", methods=["POST"])
    def new_card():
        data = request.get_json()
        
        # Create the card
        result = create_trello_card_from_excel_data(data, "Fit Up Complete.")

        if result["success"]:
            return jsonify({"message": "Card created", "card_id": result["card_id"]}), 200
        else:
            # Check if it's a duplicate job (409 Conflict) vs other errors (500)
            if "already exists in database" in result.get("error", ""):
                return jsonify({"message": "Card creation failed", "error": result["error"]}), 409
            else:
                return jsonify({"message": "Card creation failed", "error": result["error"]}), 500

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
            
            job = request.args.get('job', type=int)
            release = request.args.get('release', type=str)
            
            if not job or not release:
                return jsonify({
                    "success": False,
                    "message": "Missing required parameters",
                    "error": "Both 'job' (int) and 'release' (str) are required"
                }), 400
            
            logger.info("Adding Procore link to Trello card", job=job, release=release)
            
            result = add_procore_link_to_trello_card(job, release)
            
            if result is None:
                return jsonify({
                    "success": False,
                    "message": "Failed to add Procore link",
                    "error": "Job not found, no Trello card, or no Procore submittal found",
                    "job": job,
                    "release": release
                }), 404
            
            return jsonify({
                "success": True,
                "message": "Procore link added to Trello card successfully",
                "job": job,
                "release": release,
                "card_id": result.get("card_id"),
                "viewer_url": result.get("viewer_url"),
            }), 200
            
        except Exception as e:
            logger.error("Error adding Procore link", error=str(e), job=job, release=release)
            return jsonify({
                "success": False,
                "message": "Error adding Procore link",
                "error": str(e),
                "job": job,
                "release": release
            }), 500

    # Excel Snapshot endpoints
    @app.route("/snapshot/capture", methods=["GET", "POST"])
    def capture_snapshot():
        """Capture current Excel data as a snapshot."""
        try:
            from app.onedrive.api import capture_excel_snapshot
            result = capture_excel_snapshot()
            
            if result["success"]:
                return jsonify({
                    "message": "Snapshot captured successfully",
                    "snapshot_date": result["snapshot_date"],
                    "row_count": result["row_count"]
                }), 200
            else:
                return jsonify({
                    "message": "Failed to capture snapshot",
                    "error": result.get("error", "Unknown error")
                }), 500
                
        except Exception as e:
            logger.error("Error capturing snapshot", error=str(e))
            return jsonify({"message": "Error capturing snapshot", "error": str(e)}), 500

    @app.route("/snapshot/digest", methods=["GET", "POST"])
    def run_snapshot_digest():
        """Run Excel snapshot digest to find new rows."""
        try:
            from app.onedrive.api import run_excel_snapshot_digest
            result = run_excel_snapshot_digest()
            
            if result["success"]:
                return jsonify({
                    "message": "Snapshot digest completed",
                    "current_rows": result["current_rows"],
                    "previous_rows": result["previous_rows"],
                    "new_rows_found": result["new_rows"],
                    "snapshot_captured": result["snapshot_captured"],
                    "previous_snapshot_date": result["previous_snapshot_date"]
                }), 200
            else:
                return jsonify({
                    "message": "Snapshot digest failed",
                    "error": result.get("error", "Unknown error")
                }), 500
                
        except Exception as e:
            logger.error("Error running snapshot digest", error=str(e))
            return jsonify({"message": "Error running snapshot digest", "error": str(e)}), 500

    @app.route("/snapshot/status")
    def snapshot_status():
        """Get snapshot status and latest snapshot info."""
        try:
            from app.onedrive.api import get_latest_snapshot
            snapshot_date, df, metadata = get_latest_snapshot()
            
            status = {
                "latest_snapshot": {
                    "date": snapshot_date.isoformat() if snapshot_date else None,
                    "row_count": len(df) if df is not None else 0
                },
                "snapshots_available": snapshot_date is not None
            }
            
            return jsonify(status), 200
            
        except Exception as e:
            logger.error("Error getting snapshot status", error=str(e))
            return jsonify({"error": str(e)}), 500

    # @app.route("/seed/incremental", methods=["GET", "POST"])
    # def run_incremental_seed():
    #     """
    #     Run incremental seeding to add missing jobs from Trello/Excel cross-check.
    #     This checks the database for existing jobs and only adds new ones.
    #     """
    #     try:
    #         logger.info("Starting incremental seeding via web endpoint")
            
    #         # Get batch size from query params (default 50)
    #         batch_size = request.args.get('batch_size', 50, type=int)
    #         if batch_size < 1 or batch_size > 200:
    #             return jsonify({
    #                 "message": "Invalid batch size",
    #                 "error": "Batch size must be between 1 and 200"
    #             }), 400
            
    #         result = incremental_seed_missing_jobs(batch_size=batch_size)
            
    #         return jsonify({
    #             "message": "Incremental seeding completed successfully",
    #             "operation_id": result["operation_id"],
    #             "status": result["status"],
    #             "total_items": result["total_items"],
    #             "existing_jobs": result["existing_jobs"],
    #             "new_jobs_created": result["new_jobs_created"],
    #             "batch_size_used": batch_size
    #         }), 200
            
    #     except Exception as e:
    #         logger.error("Incremental seeding failed via web endpoint", error=str(e))
    #         return jsonify({
    #             "message": "Incremental seeding failed",
    #             "error": str(e)
    #         }), 500

    # @app.route("/seed/status")
    # def seed_status():
    #     """Get current database seeding status and job counts."""
    #     try:
    #         from app.models import Job
            
    #         total_jobs = Job.query.count()
    #         jobs_with_trello = Job.query.filter(Job.trello_card_id.isnot(None)).count()
    #         jobs_without_trello = total_jobs - jobs_with_trello
            
    #         # Get recent sync operations related to seeding
    #         recent_seed_ops = SyncOperation.query.filter(
    #             SyncOperation.operation_type.in_(['incremental_seed', 'full_seed'])
    #         ).order_by(SyncOperation.started_at.desc()).limit(5).all()
            
    #         return jsonify({
    #             "database_status": {
    #                 "total_jobs": total_jobs,
    #                 "jobs_with_trello_cards": jobs_with_trello,
    #                 "jobs_without_trello_cards": jobs_without_trello
    #             },
    #             "recent_seed_operations": [op.to_dict() for op in recent_seed_ops]
    #         }), 200
            
    #     except Exception as e:
    #         logger.error("Error getting seed status", error=str(e))
    #         return jsonify({"error": str(e)}), 500

    @app.route("/seed/cross-check", methods=["GET"])
    def get_cross_check_summary():
        """
        Get detailed summary of Trello/Excel cross-check analysis.
        Shows what jobs have Trello cards, Excel data, and database status.
        Now includes clean list of job-release identifiers that would be created.
        """
        try:
            logger.info("Getting Trello/Excel cross-check summary")
            
            summary = get_trello_excel_cross_check_summary()
            
            if "error" in summary:
                return jsonify({
                    "message": "Cross-check analysis failed",
                    "error": summary["error"]
                }), 500
            
            # Extract and format the would-be-created identifiers for cleaner display
            would_be_created = summary.get("would_be_created_identifiers", {})
            identifiers_list = would_be_created.get("identifiers", [])
            
            return jsonify({
                "message": "Cross-check analysis completed",
                "summary": summary,
                "would_be_created": {
                    "count": would_be_created.get("count", 0),
                    "identifiers": identifiers_list,
                    "identifiers_formatted": ", ".join(identifiers_list) if identifiers_list else "None"
                }
            }), 200
            
        except Exception as e:
            logger.error("Error getting cross-check summary", error=str(e))
            return jsonify({
                "message": "Cross-check analysis failed", 
                "error": str(e)
            }), 500

    @app.route("/fab-order/scan", methods=["GET"])
    def scan_fab_order():
        """
        Scan and preview how many Trello cards would be updated with Fab Order custom field.
        Only scans cards in "Released" or "Fit Up Complete" lists.
        Does not perform any updates.
        """
        try:
            from app.scripts.update_fab_order_custom_field import scan_fab_order_updates
            
            logger.info("Scanning Fab Order updates")
            result = scan_fab_order_updates(return_json=True)
            
            if "error" in result:
                return jsonify({
                    "message": "Fab Order scan failed",
                    "error": result["error"],
                    "available_fields": result.get("available_fields")
                }), 500
            
            return jsonify({
                "message": "Fab Order scan completed",
                "scan": result
            }), 200
            
        except Exception as e:
            logger.error("Error scanning Fab Order updates", error=str(e))
            return jsonify({
                "message": "Fab Order scan failed",
                "error": str(e)
            }), 500

    @app.route("/fab-order/update", methods=["POST"])
    def update_fab_order():
        """
        Update Trello cards with Fab Order custom field values from the database.
        Only updates cards in "Released" or "Fit Up Complete" lists.
        """
        try:
            from app.scripts.update_fab_order_custom_field import process_fab_order_updates
            
            logger.info("Starting Fab Order updates")
            result = process_fab_order_updates(return_json=True)
            
            if "error" in result:
                return jsonify({
                    "message": "Fab Order update failed",
                    "error": result["error"]
                }), 500
            
            return jsonify({
                "message": "Fab Order update completed",
                "update": result
            }), 200
            
        except Exception as e:
            logger.error("Error updating Fab Order", error=str(e))
            return jsonify({
                "message": "Fab Order update failed",
                "error": str(e)
            }), 500

    @app.route("/fix-trello-list/scan", methods=["GET"])
    def scan_missing_trello_list_info():
        """
        Scan and preview which cards have missing Trello list information.
        Does not perform any updates.
        
        Query params:
            job: Optional job number to filter by (int)
            release: Optional release number to filter by (str)
        """
        try:
            from app.scripts.fix_missing_trello_list_info import scan_missing_list_info
            
            # Get optional parameters
            job = request.args.get("job", type=int)
            release = request.args.get("release", type=str)
            
            logger.info(
                "Scanning for missing Trello list information",
                job=job,
                release=release
            )
            result = scan_missing_list_info(return_json=True, job=job, release=release)
            
            if "error" in result:
                return jsonify({
                    "message": "Trello list info scan failed",
                    "error": result["error"]
                }), 500
            
            return jsonify({
                "message": "Trello list info scan completed",
                "job": job,
                "release": release,
                "scan": result
            }), 200
            
        except Exception as e:
            logger.error("Error scanning Trello list info", error=str(e))
            return jsonify({
                "message": "Trello list info scan failed",
                "error": str(e)
            }), 500

    @app.route("/fix-trello-list/run", methods=["GET", "POST"])
    def fix_missing_trello_list_info():
        """
        Fix cards with missing Trello list information by fetching from Trello API.
        Actually updates the database.
        
        Query params:
            job: Optional job number to filter by (int) - if provided with release, updates only that job-release
            release: Optional release number to filter by (str) - if provided with job, updates only that job-release
            limit: Maximum number of cards to process in this request (default: 100, ignored if job+release provided)
                  Use this to process in smaller batches to avoid timeouts
            batch_size: Number of cards to commit at once (default: 50)
        """
        try:
            from app.scripts.fix_missing_trello_list_info import fix_missing_list_info, scan_missing_list_info
            
            # Get optional parameters
            job = request.args.get("job", type=int)
            release = request.args.get("release", type=str)
            limit = request.args.get("limit", type=int)
            batch_size = request.args.get("batch_size", default=50, type=int)
            
            # If job and release are provided, don't use limit (only one job-release)
            if job is not None and release is not None:
                limit = None
                logger.info(
                    "Starting fix for missing Trello list information",
                    job=job,
                    release=release,
                    batch_size=batch_size
                )
            else:
                if limit is None:
                    # Default to 100 to avoid timeouts
                    limit = 100
                logger.info(
                    "Starting fix for missing Trello list information",
                    limit=limit,
                    batch_size=batch_size,
                    job=job,
                    release=release
                )
            
            # Run the scan first to get initial state
            scan_result = scan_missing_list_info(return_json=True, job=job, release=release)
            
            if "error" in scan_result:
                return jsonify({
                    "message": "Trello list info fix failed",
                    "error": scan_result["error"]
                }), 500
            
            # Run the actual fix with limit
            fix_result = fix_missing_list_info(
                return_json=True,
                limit=limit,
                batch_size=batch_size,
                job=job,
                release=release
            )
            
            if "error" in fix_result:
                return jsonify({
                    "message": "Trello list info fix failed",
                    "error": fix_result["error"]
                }), 500
            
            # Scan again to get final state (only if not filtering by specific job-release)
            if job is not None and release is not None:
                # For single job-release, just return the fix result
                final_scan = {"message": "Single job-release update completed"}
            else:
                final_scan = scan_missing_list_info(return_json=True, job=job, release=release)
            
            return jsonify({
                "message": "Trello list info fix completed",
                "job": job,
                "release": release,
                "limit_used": limit,
                "batch_size_used": batch_size,
                "before": scan_result,
                "fix_result": fix_result,
                "after": final_scan,
                "more_remaining": final_scan.get("total_needing_fix", 0) > 0 if isinstance(final_scan, dict) else False
            }), 200
            
        except Exception as e:
            logger.error("Error fixing Trello list info", error=str(e))
            return jsonify({
                "message": "Trello list info fix failed",
                "error": str(e)
            }), 500

    @app.route("/shipping/store-at-mhmw/scan", methods=["GET"])
    def scan_store_shipping_route():
        """
        Preview which jobs would be updated to ship='ST' based on Trello list membership.
        Also cross-checks database and Trello list counts/IDs.
        """
        try:
            from app.scripts.store_shipping_sync import scan_store_shipping as scan_store_shipping_script

            limit = request.args.get("limit", type=int)

            logger.info(
                "Scanning Store at MHMW shipping sync candidates",
                limit=limit,
            )

            result = scan_store_shipping_script(return_json=True, limit=limit)

            return jsonify({
                "message": "Store at MHMW shipping scan completed",
                "scan": result
            }), 200

        except Exception as e:
            logger.error("Error scanning Store at MHMW shipping sync", error=str(e))
            return jsonify({
                "message": "Store at MHMW shipping scan failed",
                "error": str(e)
            }), 500

    @app.route("/shipping/store-at-mhmw/run", methods=["POST"])
    def run_store_shipping_sync_route():
        """
        Update jobs so their ship column is 'ST' for cards in the target Trello list,
        after verifying database and Trello list counts match.
        """
        try:
            from app.scripts.store_shipping_sync import run_store_shipping_sync as run_store_shipping_sync_script

            limit = request.args.get("limit", type=int)
            batch_size = request.args.get("batch_size", default=50, type=int)

            logger.info(
                "Running Store at MHMW shipping sync",
                limit=limit,
                batch_size=batch_size,
            )

            result = run_store_shipping_sync_script(
                return_json=True,
                limit=limit,
                batch_size=batch_size,
            )

            if result.get("aborted"):
                return jsonify({
                    "message": "Store at MHMW shipping sync aborted",
                    "reason": result.get("reason"),
                    "run": result
                }), 409

            return jsonify({
                "message": "Store at MHMW shipping sync completed",
                "run": result
            }), 200

        except Exception as e:
            logger.error("Error running Store at MHMW shipping sync", error=str(e))
            return jsonify({
                "message": "Store at MHMW shipping sync failed",
                "error": str(e)
            }), 500

    @app.route("/seed/run-one", methods=["GET", "POST"])
    def run_one_seed():
        """
        Run seeding for a single identifier.
        Query params or JSON body:
          - identifier: e.g. 1234-1 (optional; if missing, the first eligible identifier will be used)
          - dry_run: optional, default true unless auto-picking (then defaults to false)
        """
        try:
            from app.seed import process_single_identifier, get_first_identifier_to_seed
            # Support both query params and JSON body
            identifier = request.args.get("identifier") or (request.json.get("identifier") if request.is_json else None)
            dry_run_param = request.args.get("dry_run") or (request.json.get("dry_run") if request.is_json else None)

            # If no identifier provided, pick the first eligible and default dry_run to false if not specified
            if not identifier:
                identifier = get_first_identifier_to_seed()
                if not identifier:
                    return jsonify({"error": "No eligible identifiers found to seed."}), 404
                if dry_run_param is None:
                    dry_run_param = "false"

            dry_run_param = str(dry_run_param).lower() if dry_run_param is not None else "true"
            dry_run = dry_run_param in ("true", "1", "yes", "y")

            logger.info("Run-one seed request", identifier=identifier, dry_run=dry_run)
            result = process_single_identifier(identifier, dry_run=dry_run)
            return jsonify({
                "message": "Run-one completed",
                "identifier": identifier,
                "dry_run": dry_run,
                "result": result
            }), 200 if result.get("success", True) else 400
        except Exception as e:
            logger.error("Error in run-one seed", error=str(e))
            return jsonify({"error": str(e)}), 500

    # Snapshot routes
    @app.route("/snapshots/list")
    def list_snapshots():
        """List all available snapshots with basic metadata."""
        try:
            from app.config import Config
            import os
            import glob
            from datetime import datetime
            
            config = Config()
            snapshots_dir = config.SNAPSHOTS_DIR
            
            # Ensure snapshots directory exists
            os.makedirs(snapshots_dir, exist_ok=True)
            
            if not os.path.exists(snapshots_dir):
                return jsonify({
                    "snapshots": [],
                    "total_count": 0,
                    "snapshots_dir": snapshots_dir,
                    "message": "No snapshots directory found"
                }), 200
            
            # Get all snapshot files (both .pkl and _meta.json files)
            snapshot_files = glob.glob(os.path.join(snapshots_dir, "snapshot_*.pkl"))
            snapshot_files.sort(reverse=True)  # Most recent first
            
            # Debug: Print all files found in the directory
            all_files = os.listdir(snapshots_dir)
            print(f"DEBUG: All files in {snapshots_dir}: {all_files}")
            print(f"DEBUG: Snapshot .pkl files found: {snapshot_files}")
            
            snapshots = []
            for file_path in snapshot_files:
                filename = os.path.basename(file_path)
                # Extract date from filename (snapshot_YYYYMMDD.pkl or snapshot_YYYYMMDD_HHMMSS.pkl)
                try:
                    # Handle both formats: snapshot_YYYYMMDD.pkl and snapshot_YYYYMMDD_HHMMSS.pkl
                    date_str = filename.replace("snapshot_", "").replace(".pkl", "")
                    
                    # Try to parse as YYYYMMDD_HHMMSS first, then YYYYMMDD
                    try:
                        snapshot_datetime = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                        snapshot_date = snapshot_datetime.date()
                        snapshot_time = snapshot_datetime.time()
                    except ValueError:
                        # Fall back to YYYYMMDD format
                        snapshot_date = datetime.strptime(date_str, "%Y%m%d").date()
                        snapshot_time = None
                    
                    # Check if metadata file exists
                    meta_file = file_path.replace(".pkl", "_meta.json")
                    metadata = {}
                    if os.path.exists(meta_file):
                        import json
                        with open(meta_file, 'r') as f:
                            metadata = json.load(f)
                    
                    # Get file size
                    file_size = os.path.getsize(file_path)
                    
                    snapshots.append({
                        "filename": filename,
                        "date": snapshot_date.isoformat(),
                        "time": snapshot_time.isoformat() if snapshot_time else None,
                        "file_size_bytes": file_size,
                        "file_size_mb": round(file_size / (1024 * 1024), 2),
                        "row_count": metadata.get("row_count", 0),
                        "captured_at": metadata.get("captured_at"),
                        "source_file": metadata.get("source_file")
                    })
                except ValueError:
                    # Skip files that don't match expected format
                    continue
            
            return jsonify({
                "snapshots": snapshots,
                "total_count": len(snapshots),
                "snapshots_dir": snapshots_dir
            }), 200
            
        except Exception as e:
            logger.error("Error listing snapshots", error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/snapshots/compare")
    def compare_snapshots():
        """Compare two snapshots and return differences."""
        try:
            from app.onedrive.api import load_snapshot, find_new_rows_in_excel
            from datetime import datetime
            import pandas as pd
            
            # Get parameters
            current_date_str = request.args.get('current')
            previous_date_str = request.args.get('previous')
            
            if not current_date_str or not previous_date_str:
                return jsonify({
                    "error": "Both 'current' and 'previous' date parameters are required (format: YYYY-MM-DD)"
                }), 400
            
            try:
                current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()
                previous_date = datetime.strptime(previous_date_str, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({
                    "error": "Invalid date format. Use YYYY-MM-DD"
                }), 400
            
            # Load snapshots
            current_df, current_metadata = load_snapshot(current_date)
            previous_df, previous_metadata = load_snapshot(previous_date)
            
            if current_df is None:
                return jsonify({
                    "error": f"Current snapshot not found for date: {current_date_str}"
                }), 404
            
            if previous_df is None:
                return jsonify({
                    "error": f"Previous snapshot not found for date: {previous_date_str}"
                }), 404
            
            # Find differences
            new_rows = find_new_rows_in_excel(current_df, previous_df)
            
            # Calculate basic statistics
            current_count = len(current_df)
            previous_count = len(previous_df)
            new_count = len(new_rows)
            
            # Get column information
            current_columns = list(current_df.columns)
            previous_columns = list(previous_df.columns)
            
            # Check for column differences
            columns_added = set(current_columns) - set(previous_columns)
            columns_removed = set(previous_columns) - set(current_columns)
            columns_unchanged = set(current_columns) & set(previous_columns)
            
            # Prepare new rows data for JSON serialization
            new_rows_data = []
            if not new_rows.empty:
                # Convert DataFrame to list of dictionaries
                new_rows_data = new_rows.to_dict(orient='records')
                
                # Convert any non-serializable objects
                for row in new_rows_data:
                    for key, value in row.items():
                        if pd.isna(value):
                            row[key] = None
                        elif isinstance(value, (pd.Timestamp, datetime)):
                            row[key] = value.isoformat()
                        elif hasattr(value, 'item'):  # numpy types
                            row[key] = value.item()
            
            return jsonify({
                "comparison": {
                    "current_date": current_date_str,
                    "previous_date": previous_date_str,
                    "current_metadata": current_metadata,
                    "previous_metadata": previous_metadata
                },
                "statistics": {
                    "current_row_count": current_count,
                    "previous_row_count": previous_count,
                    "new_rows_count": new_count,
                    "rows_added": new_count,
                    "rows_removed": previous_count - (current_count - new_count),
                    "net_change": current_count - previous_count
                },
                "columns": {
                    "current_columns": current_columns,
                    "previous_columns": previous_columns,
                    "columns_added": list(columns_added),
                    "columns_removed": list(columns_removed),
                    "columns_unchanged": list(columns_unchanged)
                },
                "new_rows": new_rows_data,
                "summary": {
                    "has_changes": new_count > 0 or len(columns_added) > 0 or len(columns_removed) > 0,
                    "change_type": "new_rows" if new_count > 0 else "column_changes" if (columns_added or columns_removed) else "no_changes"
                }
            }), 200
            
        except Exception as e:
            logger.error("Error comparing snapshots", error=str(e))
            return jsonify({"error": str(e)}), 500

    # Persistent disk file management routes
    @app.route("/files/list")
    def list_persistent_disk_files():
        """
        List all files on the persistent disk.
        
        Query parameters:
            path: Optional subdirectory path (defaults to SNAPSHOTS_DIR or /var/data/)
            recursive: If true, recursively list files in subdirectories (default: false)
        
        Returns:
            JSON with list of files and their metadata
        """
        try:
            from app.config import Config
            
            config = Config()
            
            # Determine base directory - check for Render persistent disk or use SNAPSHOTS_DIR
            base_path = request.args.get('path', '')
            recursive = request.args.get('recursive', 'false').lower() == 'true'
            
            # If no path specified, use SNAPSHOTS_DIR or check for /var/data/ (Render persistent disk)
            if not base_path:
                # Check if /var/data/ exists (Render persistent disk)
                if os.path.exists('/var/data'):
                    base_path = '/var/data'
                else:
                    # Fall back to SNAPSHOTS_DIR
                    base_path = config.SNAPSHOTS_DIR
            else:
                # If path is provided, resolve it relative to a safe base
                # For security, only allow paths within /var/data/ or SNAPSHOTS_DIR
                if not os.path.isabs(base_path):
                    # Relative path - resolve relative to SNAPSHOTS_DIR
                    base_path = os.path.join(config.SNAPSHOTS_DIR, base_path)
                # Ensure the path is within allowed directories
                allowed_bases = ['/var/data', config.SNAPSHOTS_DIR]
                if not any(base_path.startswith(base) for base in allowed_bases if base):
                    return jsonify({
                        "error": "Path not allowed",
                        "message": "Only paths within persistent disk are accessible"
                    }), 403
            
            # Normalize the path
            base_path = os.path.normpath(base_path)
            
            if not os.path.exists(base_path):
                return jsonify({
                    "files": [],
                    "total_count": 0,
                    "base_path": base_path,
                    "message": "Directory does not exist"
                }), 200
            
            if not os.path.isdir(base_path):
                return jsonify({
                    "error": "Path is not a directory"
                }), 400
            
            # Collect files
            files = []
            if recursive:
                # Recursive listing
                for root, dirs, filenames in os.walk(base_path):
                    for filename in filenames:
                        file_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(file_path, base_path)
                        try:
                            stat = os.stat(file_path)
                            files.append({
                                "name": filename,
                                "path": rel_path,
                                "full_path": file_path,
                                "size_bytes": stat.st_size,
                                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                "is_file": True
                            })
                        except OSError:
                            continue
            else:
                # Non-recursive listing
                try:
                    items = os.listdir(base_path)
                    for item in items:
                        item_path = os.path.join(base_path, item)
                        try:
                            stat = os.stat(item_path)
                            files.append({
                                "name": item,
                                "path": item,
                                "full_path": item_path,
                                "size_bytes": stat.st_size if os.path.isfile(item_path) else 0,
                                "size_mb": round(stat.st_size / (1024 * 1024), 2) if os.path.isfile(item_path) else 0,
                                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                "is_file": os.path.isfile(item_path),
                                "is_directory": os.path.isdir(item_path)
                            })
                        except OSError:
                            continue
                except PermissionError:
                    return jsonify({
                        "error": "Permission denied",
                        "message": f"Cannot access directory: {base_path}"
                    }), 403
            
            # Sort by modified time (newest first)
            files.sort(key=lambda x: x.get('modified_time', ''), reverse=True)
            
            return jsonify({
                "files": files,
                "total_count": len(files),
                "base_path": base_path,
                "recursive": recursive
            }), 200
            
        except Exception as e:
            logger.error("Error listing persistent disk files", error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/files/download")
    def download_persistent_disk_file():
        """
        Download a file from the persistent disk.
        
        Query parameters:
            file: Relative path to the file (required)
            path: Optional base directory (defaults to SNAPSHOTS_DIR or /var/data/)
        
        Returns:
            File download response
        """
        try:
            from app.config import Config
            from flask import send_file
            
            config = Config()
            
            file_path = request.args.get('file')
            base_path = request.args.get('path', '')
            
            if not file_path:
                return jsonify({
                    "error": "Missing required parameter",
                    "message": "The 'file' parameter is required"
                }), 400
            
            # Determine base directory
            if not base_path:
                if os.path.exists('/var/data'):
                    base_path = '/var/data'
                else:
                    base_path = config.SNAPSHOTS_DIR
            else:
                if not os.path.isabs(base_path):
                    base_path = os.path.join(config.SNAPSHOTS_DIR, base_path)
                allowed_bases = ['/var/data', config.SNAPSHOTS_DIR]
                if not any(base_path.startswith(base) for base in allowed_bases if base):
                    return jsonify({
                        "error": "Path not allowed"
                    }), 403
            
            base_path = os.path.abspath(os.path.normpath(base_path))
            
            # Construct full file path
            if os.path.isabs(file_path):
                # If absolute path, ensure it's within allowed base
                full_path = os.path.abspath(os.path.normpath(file_path))
                if not full_path.startswith(base_path):
                    return jsonify({
                        "error": "File path not allowed"
                    }), 403
            else:
                # Relative path - join with base
                full_path = os.path.abspath(os.path.normpath(os.path.join(base_path, file_path)))
                # Security check: ensure the resolved path is still within base_path
                if not full_path.startswith(base_path):
                    return jsonify({
                        "error": "File path not allowed"
                    }), 403
            
            if not os.path.exists(full_path):
                return jsonify({
                    "error": "File not found",
                    "file": file_path
                }), 404
            
            if not os.path.isfile(full_path):
                return jsonify({
                    "error": "Path is not a file",
                    "file": file_path
                }), 400
            
            # Send the file
            return send_file(
                full_path,
                as_attachment=True,
                download_name=os.path.basename(full_path)
            )
            
        except Exception as e:
            logger.error("Error downloading file", error=str(e), file=file_path)
            return jsonify({"error": str(e)}), 500

    @app.route("/files/read-pkl")
    def read_pkl_file():
        """
        Read a .pkl (pickle) file from the persistent disk and return its contents.
        
        Query parameters:
            file: Relative path to the .pkl file (required)
            path: Optional base directory (defaults to SNAPSHOTS_DIR or /var/data/)
            format: Output format - 'json' (default) or 'csv'
            limit: Optional limit on number of rows to return (default: all rows)
            offset: Optional offset for pagination (default: 0)
        
        Returns:
            JSON with file contents (DataFrame converted to records) and metadata
        """
        try:
            from app.config import Config
            import pandas as pd
            import json
            
            config = Config()
            
            file_path = request.args.get('file')
            base_path = request.args.get('path', '')
            output_format = request.args.get('format', 'json').lower()
            limit = request.args.get('limit', type=int)
            offset = request.args.get('offset', 0, type=int)
            
            if not file_path:
                return jsonify({
                    "error": "Missing required parameter",
                    "message": "The 'file' parameter is required"
                }), 400
            
            # Determine base directory
            if not base_path:
                if os.path.exists('/var/data'):
                    base_path = '/var/data'
                else:
                    base_path = config.SNAPSHOTS_DIR
            else:
                if not os.path.isabs(base_path):
                    base_path = os.path.join(config.SNAPSHOTS_DIR, base_path)
                allowed_bases = ['/var/data', config.SNAPSHOTS_DIR]
                if not any(base_path.startswith(base) for base in allowed_bases if base):
                    return jsonify({
                        "error": "Path not allowed"
                    }), 403
            
            base_path = os.path.abspath(os.path.normpath(base_path))
            
            # Construct full file path
            if os.path.isabs(file_path):
                full_path = os.path.abspath(os.path.normpath(file_path))
                if not full_path.startswith(base_path):
                    return jsonify({
                        "error": "File path not allowed"
                    }), 403
            else:
                full_path = os.path.abspath(os.path.normpath(os.path.join(base_path, file_path)))
                if not full_path.startswith(base_path):
                    return jsonify({
                        "error": "File path not allowed"
                    }), 403
            
            if not os.path.exists(full_path):
                return jsonify({
                    "error": "File not found",
                    "file": file_path
                }), 404
            
            if not full_path.endswith('.pkl'):
                return jsonify({
                    "error": "File is not a .pkl file",
                    "file": file_path
                }), 400
            
            # Read the pickle file
            try:
                df = pd.read_pickle(full_path)
            except Exception as e:
                logger.error("Error reading pickle file", error=str(e), file=full_path)
                return jsonify({
                    "error": "Failed to read pickle file",
                    "message": str(e)
                }), 500
            
            # Check if it's a DataFrame
            if not isinstance(df, pd.DataFrame):
                return jsonify({
                    "error": "Pickle file does not contain a DataFrame",
                    "type": str(type(df))
                }), 400
            
            # Get metadata if available
            metadata = None
            metadata_path = full_path.replace('.pkl', '_meta.json')
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                except Exception as e:
                    logger.warning("Could not load metadata file", error=str(e))
            
            # Apply pagination if requested
            total_rows = len(df)
            if offset > 0 or limit is not None:
                end_idx = offset + limit if limit is not None else None
                df = df.iloc[offset:end_idx]
            
            # Convert DataFrame to records
            records = df.to_dict(orient='records')
            
            # Convert non-serializable types (pandas Timestamps, numpy types, etc.)
            for record in records:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
                    elif isinstance(value, (pd.Timestamp, datetime)):
                        record[key] = value.isoformat()
                    elif hasattr(value, 'item'):  # numpy types
                        try:
                            record[key] = value.item()
                        except (ValueError, AttributeError):
                            record[key] = str(value)
            
            # Prepare response based on format
            if output_format == 'csv':
                # Return as CSV string
                csv_string = df.to_csv(index=False)
                from flask import Response
                return Response(
                    csv_string,
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={os.path.basename(full_path).replace(".pkl", ".csv")}'}
                )
            else:
                # Return as JSON
                return jsonify({
                    "file": file_path,
                    "full_path": full_path,
                    "total_rows": total_rows,
                    "returned_rows": len(records),
                    "offset": offset,
                    "limit": limit,
                    "columns": list(df.columns),
                    "metadata": metadata,
                    "data": records
                }), 200
            
        except Exception as e:
            logger.error("Error reading pkl file", error=str(e), file=file_path)
            return jsonify({"error": str(e)}), 500


    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")
    app.register_blueprint(procore_bp, url_prefix="/procore")

    # Initialize scheduler safely
    try:
        init_scheduler(app)
    except Exception as e:
        logger.error("Failed to start scheduler", error=str(e))

    return app
