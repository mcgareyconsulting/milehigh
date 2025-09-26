from flask import Flask, jsonify, request
from app.trello import trello_bp
from app.onedrive import onedrive_bp

# database imports
from app.models import db, SyncOperation, SyncLog, SyncStatus
from app.seed import seed_from_combined_data
from app.combine import combine_trello_excel_data

# scheduler imports
from apscheduler.schedulers.background import BackgroundScheduler
from app.logging_config import configure_logging, get_logger
from datetime import datetime, timedelta

# Configure logging
logger = configure_logging(log_level="INFO", log_file="logs/app.log")

def init_scheduler(app):
    """Initialize the scheduler to run the OneDrive poll every 2 minutes."""
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
        trigger="interval",
        minutes=2,
        id="onedrive_poll",
        name="OneDrive Polling Job",
    )

    scheduler.start()
    logger.info("OneDrive polling scheduler started", interval_minutes=2)
    return scheduler

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

    # Index route
    @app.route("/")
    def index():
        return "Welcome to the Trello OneDrive Sync App!"

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
        """Get recent sync operations with optional filtering."""
        try:
            # Query parameters
            limit = request.args.get('limit', 50, type=int)
            status = request.args.get('status')
            operation_type = request.args.get('type')
            hours = request.args.get('hours', 24, type=int)
            
            # Build query
            query = SyncOperation.query
            if status:
                query = query.filter(SyncOperation.status == status)
            if operation_type:
                query = query.filter(SyncOperation.operation_type == operation_type)
            if hours:
                since = datetime.utcnow() - timedelta(hours=hours)
                query = query.filter(SyncOperation.started_at >= since)
            
            # Get results
            operations = query.order_by(SyncOperation.started_at.desc()).limit(limit).all()
            
            return jsonify({
                'operations': [op.to_dict() for op in operations],
                'total': len(operations),
                'filters': {
                    'limit': limit,
                    'status': status,
                    'type': operation_type,
                    'hours': hours
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
                    'timestamp': log.timestamp.isoformat(),
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

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    # Start the scheduler
    init_scheduler(app)

    return app
