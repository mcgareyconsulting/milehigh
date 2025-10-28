import os
from flask import Flask, jsonify, request
from app.trello import trello_bp
from app.onedrive import onedrive_bp
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
        minute="38",
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

    @app.route("/seed/incremental", methods=["GET", "POST"])
    def run_incremental_seed():
        """
        Run incremental seeding to add missing jobs from Trello/Excel cross-check.
        This checks the database for existing jobs and only adds new ones.
        """
        try:
            logger.info("Starting incremental seeding via web endpoint")
            
            # Get batch size from query params (default 50)
            batch_size = request.args.get('batch_size', 50, type=int)
            if batch_size < 1 or batch_size > 200:
                return jsonify({
                    "message": "Invalid batch size",
                    "error": "Batch size must be between 1 and 200"
                }), 400
            
            result = incremental_seed_missing_jobs(batch_size=batch_size)
            
            return jsonify({
                "message": "Incremental seeding completed successfully",
                "operation_id": result["operation_id"],
                "status": result["status"],
                "total_items": result["total_items"],
                "existing_jobs": result["existing_jobs"],
                "new_jobs_created": result["new_jobs_created"],
                "batch_size_used": batch_size
            }), 200
            
        except Exception as e:
            logger.error("Incremental seeding failed via web endpoint", error=str(e))
            return jsonify({
                "message": "Incremental seeding failed",
                "error": str(e)
            }), 500

    @app.route("/seed/status")
    def seed_status():
        """Get current database seeding status and job counts."""
        try:
            from app.models import Job
            
            total_jobs = Job.query.count()
            jobs_with_trello = Job.query.filter(Job.trello_card_id.isnot(None)).count()
            jobs_without_trello = total_jobs - jobs_with_trello
            
            # Get recent sync operations related to seeding
            recent_seed_ops = SyncOperation.query.filter(
                SyncOperation.operation_type.in_(['incremental_seed', 'full_seed'])
            ).order_by(SyncOperation.started_at.desc()).limit(5).all()
            
            return jsonify({
                "database_status": {
                    "total_jobs": total_jobs,
                    "jobs_with_trello_cards": jobs_with_trello,
                    "jobs_without_trello_cards": jobs_without_trello
                },
                "recent_seed_operations": [op.to_dict() for op in recent_seed_ops]
            }), 200
            
        except Exception as e:
            logger.error("Error getting seed status", error=str(e))
            return jsonify({"error": str(e)}), 500

    @app.route("/seed/cross-check", methods=["GET"])
    def get_cross_check_summary():
        """
        Get detailed summary of Trello/Excel cross-check analysis.
        Shows what jobs have Trello cards, Excel data, and database status.
        """
        try:
            logger.info("Getting Trello/Excel cross-check summary")
            
            summary = get_trello_excel_cross_check_summary()
            
            if "error" in summary:
                return jsonify({
                    "message": "Cross-check analysis failed",
                    "error": summary["error"]
                }), 500
            
            return jsonify({
                "message": "Cross-check analysis completed",
                "summary": summary
            }), 200
            
        except Exception as e:
            logger.error("Error getting cross-check summary", error=str(e))
            return jsonify({
                "message": "Cross-check analysis failed", 
                "error": str(e)
            }), 500

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


    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    # Initialize scheduler safely
    try:
        init_scheduler(app)
    except Exception as e:
        logger.error("Failed to start scheduler", error=str(e))

    return app
