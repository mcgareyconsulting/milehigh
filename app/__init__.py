import os
from flask import Flask, jsonify, request
from app.trello import trello_bp
from app.onedrive import onedrive_bp
from app.trello.api import create_trello_card_from_excel_data

# database imports
from app.models import db, SyncOperation, SyncLog, SyncStatus, JobChange
from app.change_tracker import (
    get_job_changes, get_job_change_summary, get_field_change_history, get_recent_changes,
    get_job_changes_by_release, get_job_change_summary_by_release, get_field_change_history_by_release
)
from app.seed import seed_from_combined_data
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
    # if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not os.environ.get("IS_RENDER_SCHEDULER"):
    #     logger.info("Skipping scheduler startup on this worker")
    #     return None

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
        minute="21",
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

    # Job changes by job-release endpoints
    @app.route("/jobs/<job_release>/changes")
    def get_job_changes_by_release_endpoint(job_release):
        """Get change history for a specific job-release."""
        try:
            # Query parameters
            field_name = request.args.get('field')
            source_system = request.args.get('source')
            limit = request.args.get('limit', 100, type=int)
            offset = request.args.get('offset', 0, type=int)
            
            # Date range filters
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            
            start_date = None
            end_date = None
            if start_date_str:
                start_date = datetime.fromisoformat(start_date_str + "T00:00:00")
            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str + "T23:59:59.999999")
            
            changes = get_job_changes_by_release(
                job_release=job_release,
                field_name=field_name,
                source_system=source_system,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset
            )
            
            return jsonify({
                'job_release': job_release,
                'changes': [change.to_dict() for change in changes],
                'total': len(changes),
                'filters': {
                    'field': field_name,
                    'source': source_system,
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'limit': limit,
                    'offset': offset
                }
            }), 200
            
        except Exception as e:
            logger.error("Error getting job changes by release", job_release=job_release, error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/jobs/<job_release>/changes/summary")
    def get_job_change_summary_by_release_endpoint(job_release):
        """Get a summary of all changes for a specific job-release."""
        try:
            summary = get_job_change_summary_by_release(job_release)
            return jsonify(summary), 200
            
        except Exception as e:
            logger.error("Error getting job change summary by release", job_release=job_release, error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/jobs/<job_release>/changes/field/<field_name>")
    def get_field_change_history_by_release_endpoint(job_release, field_name):
        """Get change history for a specific field of a job-release."""
        try:
            limit = request.args.get('limit', 50, type=int)
            changes = get_field_change_history_by_release(job_release, field_name, limit)
            
            return jsonify({
                'job_release': job_release,
                'field_name': field_name,
                'changes': [change.to_dict() for change in changes],
                'total': len(changes)
            }), 200
            
        except Exception as e:
            logger.error("Error getting field change history by release", 
                        job_release=job_release, 
                        field_name=field_name, 
                        error=str(e))
            return jsonify({"error": str(e)}), 500

    # Job changes HTML dashboard
    @app.route('/jobs/<int:job_id>/changes/view')
    def job_changes_view(job_id):
        """HTML view for job changes."""
        try:
            # Get job info
            from app.models import Job
            job = Job.query.get_or_404(job_id)
            
            # Get changes
            changes = get_job_changes(job_id=job_id, limit=100)
            
            from flask import render_template_string
            html = render_template_string(
                """
                <html>
                  <head>
                    <title>Job Changes - {{ job.job }}-{{ job.release }}</title>
                    <style>
                      body { font-family: Arial, sans-serif; margin: 16px; }
                      table { border-collapse: collapse; width: 100%; }
                      th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                      th { background: #f4f4f4; }
                      .field-name { font-weight: bold; color: #2c5aa0; }
                      .old-value { color: #d32f2f; }
                      .new-value { color: #388e3c; }
                      .source-trello { background: #e3f2fd; }
                      .source-excel { background: #f3e5f5; }
                      .source-system { background: #fff3e0; }
                      .muted { color: #666; font-size: 12px; }
                    </style>
                  </head>
                  <body>
                    <h2>Job Changes: {{ job.job }}-{{ job.release }} - {{ job.job_name }}</h2>
                    <p class="muted">
                      <a href="/jobs">Back to jobs</a> | 
                      <a href="/jobs/{{ job_id }}/changes/summary">Summary</a>
                    </p>
                    
                    {% if changes %}
                      <table>
                        <thead>
                          <tr>
                            <th>Changed At</th>
                            <th>Field</th>
                            <th>Old Value</th>
                            <th>New Value</th>
                            <th>Source</th>
                            <th>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {% for change in changes %}
                            <tr class="source-{{ change.source_system.lower() }}">
                              <td>{{ change.changed_at }}</td>
                              <td class="field-name">{{ change.field_name }}</td>
                              <td class="old-value">{{ change.old_value or '' }}</td>
                              <td class="new-value">{{ change.new_value or '' }}</td>
                              <td>{{ change.source_system }}</td>
                              <td>{{ change.change_type }}</td>
                            </tr>
                          {% endfor %}
                        </tbody>
                      </table>
                      <p class="muted">Total changes: {{ changes|length }}</p>
                    {% else %}
                      <p>No changes found for this job.</p>
                    {% endif %}
                  </body>
                </html>
                """,
                job=job,
                job_id=job_id,
                changes=[change.to_dict() for change in changes]
            )
            return html
        except Exception as e:
            logger.error("Error rendering job changes view", job_id=job_id, error=str(e))
            return "Error", 500

    @app.route('/jobs/<job_release>/changes/view')
    def job_changes_by_release_view(job_release):
        """HTML view for job changes by job-release."""
        try:
            # Get job info by job-release
            from app.models import Job
            job = Job.query.filter_by(job=int(job_release.split('-')[0]), release=job_release.split('-')[1]).first()
            if not job:
                return f"Job {job_release} not found", 404
            
            # Get changes
            changes = get_job_changes_by_release(job_release=job_release, limit=100)
            
            from flask import render_template_string
            html = render_template_string(
                """
                <html>
                  <head>
                    <title>Job Changes - {{ job_release }}</title>
                    <style>
                      body { font-family: Arial, sans-serif; margin: 16px; }
                      table { border-collapse: collapse; width: 100%; }
                      th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                      th { background: #f4f4f4; }
                      .field-name { font-weight: bold; color: #2c5aa0; }
                      .old-value { color: #d32f2f; }
                      .new-value { color: #388e3c; }
                      .source-trello { background: #e3f2fd; }
                      .source-excel { background: #f3e5f5; }
                      .source-system { background: #fff3e0; }
                      .muted { color: #666; font-size: 12px; }
                    </style>
                  </head>
                  <body>
                    <h2>Job Changes: {{ job_release }} - {{ job.job_name }}</h2>
                    <p class="muted">
                      <a href="/jobs">Back to jobs</a> | 
                      <a href="/jobs/{{ job_release }}/changes/summary">Summary</a>
                    </p>
                    
                    {% if changes %}
                      <table>
                        <thead>
                          <tr>
                            <th>Changed At</th>
                            <th>Field</th>
                            <th>Old Value</th>
                            <th>New Value</th>
                            <th>Source</th>
                            <th>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {% for change in changes %}
                            <tr class="source-{{ change.source_system.lower() }}">
                              <td>{{ change.changed_at }}</td>
                              <td class="field-name">{{ change.field_name }}</td>
                              <td class="old-value">{{ change.old_value or '' }}</td>
                              <td class="new-value">{{ change.new_value or '' }}</td>
                              <td>{{ change.source_system }}</td>
                              <td>{{ change.change_type }}</td>
                            </tr>
                          {% endfor %}
                        </tbody>
                      </table>
                      <p class="muted">Total changes: {{ changes|length }}</p>
                    {% else %}
                      <p>No changes found for this job.</p>
                    {% endif %}
                  </body>
                </html>
                """,
                job=job,
                job_release=job_release,
                changes=[change.to_dict() for change in changes]
            )
            return html
        except Exception as e:
            logger.error("Error rendering job changes view by release", job_release=job_release, error=str(e))
            return "Error", 500

    @app.route('/changes/recent/view')
    def recent_changes_view():
        """HTML view for recent changes across all jobs."""
        try:
            hours = request.args.get('hours', 24, type=int)
            changes = get_recent_changes(hours=hours, limit=100)
            
            from flask import render_template_string
            html = render_template_string(
                """
                <html>
                  <head>
                    <title>Recent Changes</title>
                    <style>
                      body { font-family: Arial, sans-serif; margin: 16px; }
                      table { border-collapse: collapse; width: 100%; }
                      th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                      th { background: #f4f4f4; }
                      .field-name { font-weight: bold; color: #2c5aa0; }
                      .old-value { color: #d32f2f; }
                      .new-value { color: #388e3c; }
                      .source-trello { background: #e3f2fd; }
                      .source-excel { background: #f3e5f5; }
                      .source-system { background: #fff3e0; }
                      .muted { color: #666; font-size: 12px; }
                    </style>
                  </head>
                  <body>
                    <h2>Recent Changes (Last {{ hours }} hours)</h2>
                    <p class="muted">
                      <a href="/jobs">All Jobs</a> | 
                      <a href="/changes/stats">Statistics</a>
                    </p>
                    
                    {% if changes %}
                      <table>
                        <thead>
                          <tr>
                            <th>Changed At</th>
                            <th>Job ID</th>
                            <th>Field</th>
                            <th>Old Value</th>
                            <th>New Value</th>
                            <th>Source</th>
                            <th>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {% for change in changes %}
                            <tr class="source-{{ change.source_system.lower() }}">
                              <td>{{ change.changed_at }}</td>
                              <td><a href="/jobs/{{ change.job_id }}/changes/view">{{ change.job_id }}</a></td>
                              <td class="field-name">{{ change.field_name }}</td>
                              <td class="old-value">{{ change.old_value or '' }}</td>
                              <td class="new-value">{{ change.new_value or '' }}</td>
                              <td>{{ change.source_system }}</td>
                              <td>{{ change.change_type }}</td>
                            </tr>
                          {% endfor %}
                        </tbody>
                      </table>
                      <p class="muted">Total changes: {{ changes|length }}</p>
                    {% else %}
                      <p>No recent changes found.</p>
                    {% endif %}
                  </body>
                </html>
                """,
                hours=hours,
                changes=[change.to_dict() for change in changes]
            )
            return html
        except Exception as e:
            logger.error("Error rendering recent changes view", error=str(e))
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

    # Job change history endpoints
    @app.route("/jobs/<int:job_id>/changes")
    def get_job_changes_endpoint(job_id):
        """Get change history for a specific job."""
        try:
            # Query parameters
            field_name = request.args.get('field')
            source_system = request.args.get('source')
            limit = request.args.get('limit', 100, type=int)
            offset = request.args.get('offset', 0, type=int)
            
            # Date range filters
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            
            start_date = None
            end_date = None
            if start_date_str:
                start_date = datetime.fromisoformat(start_date_str + "T00:00:00")
            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str + "T23:59:59.999999")
            
            changes = get_job_changes(
                job_id=job_id,
                field_name=field_name,
                source_system=source_system,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset
            )
            
            return jsonify({
                'job_id': job_id,
                'changes': [change.to_dict() for change in changes],
                'total': len(changes),
                'filters': {
                    'field': field_name,
                    'source': source_system,
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'limit': limit,
                    'offset': offset
                }
            }), 200
            
        except Exception as e:
            logger.error("Error getting job changes", job_id=job_id, error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/jobs/<int:job_id>/changes/summary")
    def get_job_change_summary_endpoint(job_id):
        """Get a summary of all changes for a specific job."""
        try:
            summary = get_job_change_summary(job_id)
            return jsonify(summary), 200
            
        except Exception as e:
            logger.error("Error getting job change summary", job_id=job_id, error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/jobs/<int:job_id>/changes/field/<field_name>")
    def get_field_change_history_endpoint(job_id, field_name):
        """Get change history for a specific field of a job."""
        try:
            limit = request.args.get('limit', 50, type=int)
            changes = get_field_change_history(job_id, field_name, limit)
            
            return jsonify({
                'job_id': job_id,
                'field_name': field_name,
                'changes': [change.to_dict() for change in changes],
                'total': len(changes)
            }), 200
            
        except Exception as e:
            logger.error("Error getting field change history", 
                        job_id=job_id, 
                        field_name=field_name, 
                        error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/changes/recent")
    def get_recent_changes_endpoint():
        """Get recent changes across all jobs."""
        try:
            hours = request.args.get('hours', 24, type=int)
            limit = request.args.get('limit', 100, type=int)
            
            changes = get_recent_changes(hours=hours, limit=limit)
            
            return jsonify({
                'changes': [change.to_dict() for change in changes],
                'total': len(changes),
                'filters': {
                    'hours': hours,
                    'limit': limit
                }
            }), 200
            
        except Exception as e:
            logger.error("Error getting recent changes", error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/changes/stats")
    def get_change_stats_endpoint():
        """Get statistics about job changes."""
        try:
            from sqlalchemy import func, desc
            from datetime import timedelta
            
            # Recent changes count by source system
            recent_changes = JobChange.query.filter(
                JobChange.changed_at >= datetime.utcnow() - timedelta(hours=24)
            ).all()
            
            source_counts = {}
            field_counts = {}
            change_type_counts = {}
            
            for change in recent_changes:
                # Count by source system
                source = change.source_system
                source_counts[source] = source_counts.get(source, 0) + 1
                
                # Count by field
                field = change.field_name
                field_counts[field] = field_counts.get(field, 0) + 1
                
                # Count by change type
                change_type = change.change_type
                change_type_counts[change_type] = change_type_counts.get(change_type, 0) + 1
            
            # Most active jobs (by change count)
            most_active_jobs = db.session.query(
                JobChange.job_id,
                func.count(JobChange.id).label('change_count')
            ).filter(
                JobChange.changed_at >= datetime.utcnow() - timedelta(days=7)
            ).group_by(JobChange.job_id)\
             .order_by(desc('change_count'))\
             .limit(10)\
             .all()
            
            return jsonify({
                'last_24_hours': {
                    'total_changes': len(recent_changes),
                    'by_source_system': source_counts,
                    'by_field': field_counts,
                    'by_change_type': change_type_counts
                },
                'most_active_jobs_7_days': [
                    {'job_id': job_id, 'change_count': count} 
                    for job_id, count in most_active_jobs
                ]
            }), 200
            
        except Exception as e:
            logger.error("Error getting change stats", error=str(e))
            return jsonify({"error": str(e)}), 500


    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    # Initialize scheduler safely
    try:
        init_scheduler(app)
    except Exception as e:
        logger.error("Failed to start scheduler", error=str(e))

    return app
