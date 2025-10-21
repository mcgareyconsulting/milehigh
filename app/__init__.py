import os
from flask import Flask, jsonify, request
from app.trello import trello_bp
from app.onedrive import onedrive_bp
from app.trello.api import create_trello_card_from_excel_data

# database imports
from app.models import db, SyncOperation, SyncLog, SyncStatus
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

def init_scheduler(app):
    """Initialize the scheduler to run the OneDrive poll every hour on the hour."""
    from app.onedrive.utils import run_onedrive_poll
    from app.sync_lock import sync_lock_manager

    scheduler = BackgroundScheduler()

    def scheduled_run():
        with app.app_context():
            if sync_lock_manager.is_locked():
                current_op = sync_lock_manager.get_current_operation()
                logger.info(
                    "Skipping scheduled OneDrive poll - sync locked",
                    current_operation=current_op
                )
                # If OneDrive poll is skipped, try draining Trello queue lightly
                try:
                    from app.trello import drain_trello_queue
                    drained = drain_trello_queue(max_items=3)
                    if drained:
                        logger.info("Drained Trello queue while OneDrive locked", drained=drained)
                except Exception as e:
                    logger.warning("Trello queue drain failed during skip", error=str(e))
                return

            try:
                logger.info("Starting scheduled OneDrive poll")
                # Before starting OneDrive poll, opportunistically drain a few Trello events if free
                try:
                    from app.trello import drain_trello_queue
                    drained_pre = drain_trello_queue(max_items=2)
                    if drained_pre:
                        logger.info("Pre-drain Trello queue", drained=drained_pre)
                except Exception:
                    pass

                run_onedrive_poll()

                # After poll, drain a few more Trello events
                try:
                    from app.trello import drain_trello_queue
                    drained_post = drain_trello_queue(max_items=5)
                    if drained_post:
                        logger.info("Post-drain Trello queue", drained=drained_post)
                except Exception:
                    pass
                logger.info("Scheduled OneDrive poll completed successfully")

            except RuntimeError as e:
                logger.info("Scheduled OneDrive poll skipped due to lock", error=str(e))

            except Exception as e:
                logger.error("Scheduled OneDrive poll failed", error=str(e))

    scheduler.add_job(
        func=scheduled_run,
        trigger="cron",
        minute="0",  # Run at minute 0 of every hour
        hour="*",  # Every hour (0-23)
        day="*",   # Every day
        month="*", # Every month
        day_of_week="*",  # Every day of the week
        id="onedrive_poll",
        name="OneDrive Polling Job",
    )

    scheduler.start()
    logger.info("OneDrive polling scheduler started", schedule="every hour on the hour")
    return scheduler

def create_app():
    app = Flask(__name__)
    
    # Database configuration - use environment variable for production
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # For production databases (PostgreSQL, MySQL, etc.)
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        
        # Add SSL configuration for PostgreSQL connections
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,  # Verify connections before use
            "pool_recycle": 300,    # Recycle connections every 5 minutes
            "pool_size": 10,        # Number of connections to maintain
            "max_overflow": 20,     # Additional connections beyond pool_size
            "pool_timeout": 30,     # Seconds to wait for connection from pool
            "connect_args": {
                "sslmode": "require",  # Require SSL for production security
                "connect_timeout": 10,
                "application_name": "trello_sharepoint_app",
                "options": "-c statement_timeout=30000"  # 30 second statement timeout
            }
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


    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    # Start the scheduler
    init_scheduler(app)

    return app
