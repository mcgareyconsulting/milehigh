import os
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

# Blueprints
from app.trello import trello_bp
from app.procore import procore_bp
from app.brain import brain_bp

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
    logger.info(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')[:50]}...")

   # Get allowed origins from environment variable
    allowed_origins = app.config.get("CORS_ORIGINS", "*")
    if allowed_origins != "*":
        # Parse comma-separated list if provided
        allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]
    
    # Enable CORS for React frontend
    # Use a simpler configuration that applies to all routes
    # This ensures CORS headers are always sent, even on errors
    CORS(app, 
         resources={r"/*": {"origins": allowed_origins}},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])

    # Configure React frontend serving
    FRONTEND_BUILD_DIR = Path(__file__).parent.parent / 'frontend' / 'dist'
    
    # List of API route prefixes to exclude from React catch-all
    API_ROUTE_PREFIXES = [
        'api/',
        'jobs/',  # API endpoint: /jobs (GET) - note the trailing slash
        'sync/',
        'trello/',
        'procore/',
        'shipping/',
        'files/',
        'seed/',
        'fab-order/',
        'fix-trello-list/',
        'name-check/',
        'db-comparison',
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
        outbox_thread = threading.Thread(target=outbox_retry_worker, daemon=True, name="outbox-retry-worker")
        outbox_thread.start()
        logger.info("Outbox retry worker thread started successfully")
        
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
        'frontend',
        'dist'
    )

    # Jobs route - display all jobs in database
    def determine_stage_from_db_fields(job):
        """
        Get the stage from the job's stage field.
        Returns the stage name or 'Released' if the stage field is None/empty.
        """
        # Use stage field directly from database
        if hasattr(job, 'stage') and job.stage:
            return job.stage
        return 'Released'

    # Index route - serve React app
    @app.route("/")
    def index():
        if FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / 'index.html').exists():
            return send_file(FRONTEND_BUILD_DIR / 'index.html')
        return "Welcome to the Trello OneDrive Sync App! (React build not found. Run 'npm run build' in frontend directory.)", 200

    # Job Log route - serve React app
    # DISABLED: Job log functionality not working yet
    @app.route("/job-log")
    def job_log():
        """Serve the React app for the Job Log page. Frontend will call /api/jobs for data."""
        if FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / 'index.html').exists():
            return send_file(FRONTEND_BUILD_DIR / 'index.html')
        return "React build not found. Run 'npm run build' in the frontend directory.", 200

    # Serve static assets from React build (JS, CSS, images, etc.)
    @app.route('/assets/<path:filename>')
    def serve_static_assets(filename):
        assets_dir = FRONTEND_BUILD_DIR / 'assets'
        if assets_dir.exists():
            return send_from_directory(assets_dir, filename)
        return "Assets not found", 404
    
    # Serve root-level static files from dist directory
    # This handles favicon, robots.txt, and any other root-level static files
    @app.route('/favicon.ico')
    @app.route('/robots.txt')
    @app.route('/vite.svg')
    @app.route('/bananas-svgrepo-com.svg')
    def serve_root_static_files():
        filename = request.path.lstrip('/')
        file_path = FRONTEND_BUILD_DIR / filename
        
        # Special handling for favicon.ico - serve SVG if .ico doesn't exist
        if filename == 'favicon.ico' and not file_path.exists():
            svg_path = FRONTEND_BUILD_DIR / 'bananas-svgrepo-com.svg'
            if svg_path.exists():
                return send_file(svg_path, mimetype='image/svg+xml')
        
        if file_path.exists() and file_path.is_file():
            return send_file(file_path)
        from flask import abort
        abort(404)

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
    @app.route("/api/jobs/<int:job>/<release>/history")
    def job_change_history_path(job, release):
        """Get change history for a specific job-release combination via URL path."""
        return _get_job_change_history(job, release)
    
    @app.route("/api/jobs/history")
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
    
    @app.route("/api/submittals/history")
    def submittal_change_history():
        """Get change history for a submittal via query parameters.
        
        Query parameters:
            submittal_id (str): Submittal ID (required)
        
        Returns:
            JSON object with history array and search metadata
        """
        submittal_id = request.args.get('submittal_id', type=str)
        return _get_submittal_change_history(submittal_id)
    
    def _extract_new_value_from_payload(action, payload):
        """
        Extract a human-readable 'new value' from the payload based on action type.
        Returns a formatted string representing the new value for display.
        """
        if not payload:
            return None
        
        # Handle different action types
        if action == 'update_stage':
            # For stage updates, extract the 'to' value
            return payload.get('to')
        
        elif action == 'list_move':
            # For list moves, show the destination list
            to_list = payload.get('to_list_name') or payload.get('to_list_id')
            from_list = payload.get('from_list_name') or payload.get('from_list_id')
            if to_list and from_list:
                return f"{to_list}"
            elif to_list:
                return to_list
            return None
        
        elif action in ['created', 'create']:
            # For created events, show key information
            if isinstance(payload, dict):
                parts = []
                if 'Job' in payload:
                    parts.append(f"Job: {payload['Job']}")
                if 'Release' in payload:
                    parts.append(f"Release: {payload['Release']}")
                return " | ".join(parts) if parts else "Job created"
            return "Job created"
        
        # For other action types, try to extract meaningful values
        if isinstance(payload, dict):
            # Try common keys that might indicate a new value
            for key in ['to', 'value', 'new_value', 'status', 'stage', 'state']:
                if key in payload:
                    return str(payload[key])
            # If no standard key, return a summary of the payload
            if len(payload) == 1:
                return str(list(payload.values())[0])
            # For complex payloads, return a summary
            return f"{len(payload)} fields updated"
        
        return str(payload) if payload else None
    
    def _get_job_change_history(job, release):
        """Internal function to retrieve job event history."""
        from app.models import JobEvents, Job
        
        # At least one parameter must be provided
        if job is None and release is None:
            return jsonify({
                'error': 'Missing required parameters',
                'message': 'At least one of job (int) or release (str) is required',
                'usage': {
                    'job_only': '/api/jobs/history?job=<int>',
                    'release_only': '/api/jobs/history?release=<str>',
                    'both': '/api/jobs/history?job=<int>&release=<str>',
                    'path': '/api/jobs/<job>/<release>/history'
                }
            }), 400
        
        try:
            # Build job events query based on provided parameters
            events_query = JobEvents.query
            
            if job is not None:
                events_query = events_query.filter_by(job=job)
            if release is not None:
                events_query = events_query.filter_by(release=str(release))
            
            # Order by most recent first
            job_events = events_query.order_by(JobEvents.created_at.desc()).all()
            
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
            
            for event in job_events:
                new_value = _extract_new_value_from_payload(event.action, event.payload)
                history.append({
                    'id': event.id,
                    'job': event.job,
                    'release': event.release,
                    'action': event.action,
                    'new_value': new_value,
                    'payload': event.payload,  # Keep full payload for reference
                    'payload_hash': event.payload_hash,
                    'source': event.source,
                    'created_at': format_datetime_mountain(event.created_at),
                    'applied_at': format_datetime_mountain(event.applied_at) if event.applied_at else None
                })
                job_releases.add((event.job, event.release))
            
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
            
            # If we have no job releases from job events, ensure we include jobs that match the query
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
            logger.error("Error getting job event history", error=str(e), job=job, release=release)
            return jsonify({
                'error': 'Failed to retrieve change history',
                'message': str(e)
            }), 500
    
    def _extract_submittal_new_value_from_payload(action, payload):
        """
        Extract a human-readable 'new value' from submittal event payload based on action type.
        Returns a formatted string representing the new value for display.
        """
        if not payload:
            return None
        
        # Handle different action types
        if action == 'created':
            # For created events, show key information
            if isinstance(payload, dict):
                parts = []
                if 'title' in payload:
                    parts.append(f"Title: {payload['title']}")
                if 'status' in payload:
                    parts.append(f"Status: {payload['status']}")
                return " | ".join(parts) if parts else "Submittal created"
            return "Submittal created"
        
        elif action == 'updated':
            # For updated events, show what changed
            if isinstance(payload, dict):
                changes = []
                if 'ball_in_court' in payload:
                    old_val = payload['ball_in_court'].get('old', 'N/A')
                    new_val = payload['ball_in_court'].get('new', 'N/A')
                    changes.append(f"Ball in Court: {old_val} → {new_val}")
                if 'status' in payload:
                    old_val = payload['status'].get('old', 'N/A')
                    new_val = payload['status'].get('new', 'N/A')
                    changes.append(f"Status: {old_val} → {new_val}")
                if 'order_bumped' in payload and payload.get('order_bumped'):
                    changes.append(f"Order bumped to {payload.get('order_number', 'N/A')}")
                return " | ".join(changes) if changes else "Submittal updated"
            return "Submittal updated"
        
        # For other action types, try to extract meaningful values
        if isinstance(payload, dict):
            # Try common keys that might indicate a new value
            for key in ['to', 'value', 'new_value', 'status', 'stage', 'state']:
                if key in payload:
                    return str(payload[key])
            # If no standard key, return a summary of the payload
            if len(payload) == 1:
                return str(list(payload.values())[0])
            # For complex payloads, return a summary
            return f"{len(payload)} fields updated"
        
        return str(payload) if payload else None
    
    def _get_submittal_change_history(submittal_id):
        """Internal function to retrieve submittal event history."""
        from app.models import SubmittalEvents, ProcoreSubmittal
        
        # submittal_id is required
        if not submittal_id:
            return jsonify({
                'error': 'Missing required parameter',
                'message': 'submittal_id (str) is required',
                'usage': {
                    'submittal_id': '/api/submittals/history?submittal_id=<str>'
                }
            }), 400
        
        try:
            # Build submittal events query
            events_query = SubmittalEvents.query.filter_by(submittal_id=str(submittal_id))
            
            # Order by most recent first
            submittal_events = events_query.order_by(SubmittalEvents.created_at.desc()).all()
            
            # Get submittal record for metadata
            submittal_record = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
            
            # Format the response
            history = []
            
            for event in submittal_events:
                new_value = _extract_submittal_new_value_from_payload(event.action, event.payload)
                history.append({
                    'id': event.id,
                    'submittal_id': event.submittal_id,
                    'action': event.action,
                    'new_value': new_value,
                    'payload': event.payload,  # Keep full payload for reference
                    'payload_hash': event.payload_hash,
                    'source': event.source,
                    'created_at': format_datetime_mountain(event.created_at),
                    'applied_at': format_datetime_mountain(event.applied_at) if event.applied_at else None
                })
            
            # Format submittal details if record exists
            submittal_details = None
            if submittal_record:
                submittal_details = {
                    'submittal_id': submittal_record.submittal_id,
                    'title': submittal_record.title,
                    'status': submittal_record.status,
                    'type': submittal_record.type,
                    'ball_in_court': submittal_record.ball_in_court,
                    'project_name': submittal_record.project_name,
                    'project_number': submittal_record.project_number
                }
            
            return jsonify({
                'search_type': 'submittal',
                'search_submittal_id': submittal_id,
                'total_changes': len(history),
                'history': history,
                'submittal_details': submittal_details
            }), 200
            
        except Exception as e:
            logger.exception("Error retrieving submittal change history")
            return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

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

    @app.route("/name-check/scan", methods=["GET"])
    def scan_card_names_route():
        """
        Scan Trello card names for accuracy (dry run, preview only).
        
        Compares DB trello_card_name with expected format: {job}-{release} {job_name} {description}
        Does not perform any updates.
        
        Query params:
            limit: Optional maximum number of jobs to process (int)
        """
        try:
            from app.scripts.name_check import check_card_names
            
            limit = request.args.get("limit", type=int)
            
            logger.info("Scanning Trello card names", limit=limit)
            result = check_card_names(return_json=True, dry_run=True, limit=limit)
            
            if "error" in result:
                return jsonify({
                    "message": "Card name scan failed",
                    "error": result["error"],
                    "error_type": result.get("error_type")
                }), 500
            
            return jsonify({
                "message": "Card name scan completed",
                "scan": result
            }), 200
            
        except Exception as e:
            logger.error("Error scanning card names", error=str(e))
            return jsonify({
                "message": "Card name scan failed",
                "error": str(e)
            }), 500

    @app.route("/name-check/update", methods=["POST"])
    def update_card_names_route():
        """
        Scan and update Trello card names that don't match expected format.
        
        Compares DB trello_card_name with expected format: {job}-{release} {job_name} {description}
        Updates both Trello API and DB trello_card_name field for cards that don't match.
        
        Query params:
            limit: Optional maximum number of jobs to process (int)
        """
        try:
            from app.scripts.name_check import check_card_names
            
            limit = request.args.get("limit", type=int)
            
            logger.info("Updating Trello card names", limit=limit)
            result = check_card_names(return_json=True, dry_run=False, limit=limit)
            
            if "error" in result:
                return jsonify({
                    "message": "Card name update failed",
                    "error": result["error"],
                    "error_type": result.get("error_type")
                }), 500
            
            return jsonify({
                "message": "Card name update completed",
                "update": result
            }), 200
            
        except Exception as e:
            logger.error("Error updating card names", error=str(e))
            return jsonify({
                "message": "Card name update failed",
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

    @app.route("/db-comparison", methods=["GET"])
    def db_comparison():
        """
        Compare sandbox and production databases to find jobs that exist in one but not the other.
        
        Returns:
            JSON response with:
            - summary: Counts of jobs in each database and differences
            - only_in_sandbox: List of jobs that exist in sandbox but not production
            - only_in_production: List of jobs that exist in production but not sandbox
            - only_in_sandbox_identifiers: Simple list of job-release identifiers (e.g., "1234-1")
            - only_in_production_identifiers: Simple list of job-release identifiers
        """
        try:
            from app.scripts.db_comparison import compare_databases
            
            logger.info("Running database comparison: sandbox vs production")
            result = compare_databases(return_json=True)
            
            if "error" in result:
                return jsonify({
                    "message": "Database comparison failed",
                    "error": result["error"]
                }), 500
            
            return jsonify({
                "message": "Database comparison completed",
                "comparison": result
            }), 200
            
        except Exception as e:
            logger.error("Error running database comparison", error=str(e), exc_info=True)
            return jsonify({
                "message": "Database comparison failed",
                "error": str(e)
            }), 500

    # Catch-all route for React Router (must be last, after all API routes)
    # This handles direct URL access to React routes like /history, /operations, etc.
    # Note: /jobs is handled above with special logic to distinguish API vs browser requests
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_react_app(path):
        # Skip if this is an API route
        if is_api_route(path):
            # Return 404 for API routes that don't exist
            from flask import abort
            abort(404)
        
        # Check if this is a static file in the dist directory (not in assets)
        # This handles any root-level static files we might have missed
        if path and not path.startswith('assets/'):
            static_file_path = FRONTEND_BUILD_DIR / path
            if static_file_path.exists() and static_file_path.is_file():
                return send_file(static_file_path)
        
        # Serve index.html for all React routes
        # React Router will handle client-side routing
        if FRONTEND_BUILD_DIR.exists() and (FRONTEND_BUILD_DIR / 'index.html').exists():
            return send_file(FRONTEND_BUILD_DIR / 'index.html')
        else:
            return "React build not found. Run 'npm run build' in the frontend directory.", 404

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(procore_bp, url_prefix="/procore")
    # app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(brain_bp, url_prefix="/brain")

    # Global error handler to ensure CORS headers are always included
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle all exceptions and ensure CORS headers are included"""
        from flask_cors import cross_origin
        
        # Log the error
        logger.error("Unhandled exception", error=str(e), exc_info=True)
        
        # Return JSON error response with proper status code
        if hasattr(e, 'code'):
            status_code = e.code
        elif hasattr(e, 'status_code'):
            status_code = e.status_code
        else:
            status_code = 500
        
        response = jsonify({
            "error": str(e),
            "message": "An error occurred processing your request"
        })
        response.status_code = status_code
        
        # CORS headers should be added automatically by Flask-CORS
        # but we ensure they're present
        return response

    return app
