# Package
import os
import json
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from app.models import db, ProcoreSubmittal

from app.procore.procore import get_project_id_by_project_name

from app.procore.helpers import clean_value

from app.logging_config import get_logger
from app.config import Config as cfg

logger = get_logger(__name__)

procore_bp = Blueprint("procore", __name__)


def log_webhook_payload(payload: dict, headers: dict = None):
    """
    Log incoming webhook payload to persistent disk (same as Excel snapshots).
    Uses JSON Lines format (one JSON object per line) for easy parsing.
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "headers": dict(headers) if headers else {},
        "payload": payload
    }
    
    # Use the same persistent disk directory as Excel snapshots
    webhook_logs_dir = cfg.SNAPSHOTS_DIR
    os.makedirs(webhook_logs_dir, exist_ok=True)
    
    # Use a subdirectory for webhook logs
    webhook_logs_path = os.path.join(webhook_logs_dir, "procore_webhook_payloads.log")
    
    # Append to log file (JSON Lines format)
    try:
        with open(webhook_logs_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        logger.info(f"Logged Procore webhook payload to {webhook_logs_path}")
    except Exception as e:
        logger.error(f"Failed to log webhook payload: {str(e)}", exc_info=True)


@procore_bp.route("/webhook", methods=["HEAD", "POST"])
def procore_webhook():
    """
    Procore webhook endpoint to receive Submittals update events.
    For now, just logs all incoming payloads to a file for debugging.
    """
    if request.method == "HEAD":
        # Procore webhook verification request
        return "", 200

    if request.method == "POST":
        try:
            # Get the raw payload
            payload = request.json if request.is_json else request.get_data(as_text=True)
            
            # Get headers for context
            headers = {k: v for k, v in request.headers}
            
            # Log the webhook payload
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    # If it's not valid JSON, log as text
                    pass
            
            log_webhook_payload(payload, headers)
            
            # Also log via application logger
            event_type = payload.get("event_type") if isinstance(payload, dict) else "unknown"
            resource_name = payload.get("resource_name") if isinstance(payload, dict) else "unknown"
            project_id = payload.get("project_id") if isinstance(payload, dict) else None
            
            logger.info(
                f"Received Procore webhook: resource={resource_name}, "
                f"event_type={event_type}, project_id={project_id}"
            )
            
            # Return 200 OK to acknowledge receipt
            return jsonify({
                "status": "received",
                "timestamp": datetime.utcnow().isoformat()
            }), 200
            
        except Exception as e:
            # Log the error but still return 200 to avoid webhook retries
            # Procore will retry if we return an error status
            logger.error(f"Error processing Procore webhook: {str(e)}", exc_info=True)
            
            # Try to log the error payload anyway
            try:
                error_payload = {
                    "error": str(e),
                    "raw_data": request.get_data(as_text=True) if hasattr(request, 'get_data') else None
                }
                log_webhook_payload(error_payload, {k: v for k, v in request.headers})
            except:
                pass
            
            return jsonify({
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }), 200

@procore_bp.route("/api/webhook/payloads", methods=["GET"])
def webhook_payloads():
    """
    API endpoint to view recent webhook payloads from the persistent disk.
    Returns the last N webhook payloads that hit the production server.
    
    Query Parameters:
    - limit: Number of payloads to return (default: 50, max: 200)
    - project_id: Filter by project_id (optional)
    - resource_name: Filter by resource_name (optional, e.g., "Submittals")
    - event_type: Filter by event_type (optional, e.g., "update")
    
    Example:
    GET /procore/api/webhook/payloads?limit=100
    GET /procore/api/webhook/payloads?limit=50&resource_name=Submittals&event_type=update
    GET /procore/api/webhook/payloads?project_id=2900844
    """
    try:
        import json as json_lib
        
        # Get query parameters
        limit = request.args.get("limit", default=50, type=int)
        limit = min(limit, 200)  # Cap at 200 for performance
        project_id_filter = request.args.get("project_id")
        resource_name_filter = request.args.get("resource_name")
        event_type_filter = request.args.get("event_type")
        
        # Use the same persistent disk directory as Excel snapshots
        webhook_logs_dir = cfg.SNAPSHOTS_DIR
        log_file = os.path.join(webhook_logs_dir, "procore_webhook_payloads.log")
        
        if not os.path.exists(log_file):
            return jsonify({
                "status": "success",
                "message": "No webhook payloads logged yet",
                "payloads": [],
                "total": 0,
                "log_file": log_file
            }), 200
        
        # Read all lines (we'll filter after parsing)
        all_payloads = []
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            payload = json_lib.loads(line)
                            all_payloads.append(payload)
                        except json_lib.JSONDecodeError:
                            continue
            
            # Filter payloads based on query parameters
            filtered_payloads = []
            for payload in all_payloads:
                payload_data = payload.get("payload", {})
                if isinstance(payload_data, str):
                    try:
                        payload_data = json_lib.loads(payload_data)
                    except:
                        payload_data = {}
                
                # Apply filters
                if project_id_filter:
                    payload_project_id = payload_data.get("project_id") or payload_data.get("project", {}).get("id")
                    if str(payload_project_id) != str(project_id_filter):
                        continue
                
                if resource_name_filter:
                    payload_resource = payload_data.get("resource_name") or payload_data.get("resource", {}).get("name")
                    if payload_resource != resource_name_filter:
                        continue
                
                if event_type_filter:
                    payload_event = payload_data.get("event_type") or payload_data.get("event", {}).get("type")
                    if payload_event != event_type_filter:
                        continue
                
                filtered_payloads.append(payload)
            
            # Sort by timestamp (most recent first)
            filtered_payloads.sort(
                key=lambda x: x.get("timestamp", ""), 
                reverse=True
            )
            
            # Limit results
            payloads = filtered_payloads[:limit]
            
        except Exception as e:
            logger.error(f"Error reading webhook payloads: {str(e)}", exc_info=True)
            return jsonify({
                "status": "error",
                "error": f"Failed to read log file: {str(e)}",
                "log_file": log_file
            }), 500
        
        return jsonify({
            "status": "success",
            "payloads": payloads,
            "total": len(payloads),
            "total_matching": len(filtered_payloads),
            "limit": limit,
            "filters": {
                "project_id": project_id_filter,
                "resource_name": resource_name_filter,
                "event_type": event_type_filter
            },
            "log_file": log_file
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving webhook payloads: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@procore_bp.route("/api/drafting-work-load", methods=["GET"])
def drafting_work_load():
    """Return Drafting Work Load data from the db"""
    submittals = ProcoreSubmittal.query.all()
    return jsonify({
        "submittals": [submittal.to_dict() for submittal in submittals]
    }), 200

@procore_bp.route("/api/upload/drafting-workload-submittals", methods=["POST"])
def drafting_workload_submittals():
    """Upload a new Drafting Work Load Excel file and save to DB"""
    try:
        # Validate file presence
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Read Excel file
        try:
            df = pd.read_excel(file)
        except Exception as exc:
            logger.error(f"Error reading Excel file: {str(exc)}", exc_info=True)
            return jsonify({'error': f'Failed to read Excel file: {str(exc)}'}), 400

        # Validate required columns
        required_columns = ['Submittals Id', 'Project Name', 'Project Number', 'Title', 
                          'Ball In Court Due Date', 'Status', 'Type', 'Ball In Court', 
                          'Submittal Manager']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"Missing required columns: {missing_columns}")
            return jsonify({'error': f'Missing required columns: {", ".join(missing_columns)}'}), 400

        # Helper function to safely get row value
        def safe_get(row, col, default=None):
            if col not in df.columns:
                return default
            try:
                value = row[col]
                if pd.isna(value):
                    return default
                return value
            except (KeyError, IndexError):
                return default

        # drop all columns in procoresubmittal table
        try:
            ProcoreSubmittal.query.delete()
            db.session.commit()
        except Exception as exc:
            logger.error(f"Error deleting existing records: {str(exc)}", exc_info=True)
            db.session.rollback()
            return jsonify({'error': f'Failed to clear existing records: {str(exc)}'}), 500

        # Cache project id lookups
        project_id_cache = {}
        skipped_count = 0
        inserted_count = 0
        error_count = 0

        for idx, row in df.iterrows():
            try:
                # Get and validate submittal_id
                submittal_id_raw = safe_get(row, 'Submittals Id')
                if submittal_id_raw is None:
                    skipped_count += 1
                    logger.warning(f"Row {idx}: Missing Submittals Id, skipping")
                    continue
                
                submittal_id = str(submittal_id_raw).strip()
                if not submittal_id:
                    skipped_count += 1
                    logger.warning(f"Row {idx}: Empty Submittals Id, skipping")
                    continue

                # Check if already exists (shouldn't happen after delete, but check anyway)
                if ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first():
                    skipped_count += 1
                    continue

                project_name = safe_get(row, 'Project Name', '').strip()
                if not project_name:
                    skipped_count += 1
                    logger.warning(f"Row {idx}: Missing Project Name, skipping")
                    continue

                # Get project_id from cache or API
                if project_name not in project_id_cache:
                    try:
                        project_id = get_project_id_by_project_name(project_name)
                        project_id_cache[project_name] = project_id
                    except Exception as exc:
                        logger.error(f"Error getting project_id for '{project_name}': {str(exc)}")
                        project_id = None
                        project_id_cache[project_name] = None
                else:
                    project_id = project_id_cache[project_name]

                # Convert project_id to string if it exists
                if project_id is not None:
                    project_id = str(project_id)

                # Insert/update in DB with cleaned values
                submittal = ProcoreSubmittal(
                    submittal_id=submittal_id,
                    procore_project_id=project_id,
                    project_number=str(safe_get(row, 'Project Number', '') or '').strip() or None,
                    project_name=project_name,
                    title=str(safe_get(row, 'Title', '') or '').strip() or None,
                    ball_in_court_due_date=clean_value(safe_get(row, 'Ball In Court Due Date')),
                    status=str(safe_get(row, 'Status', '') or '').strip() or None,
                    type=str(safe_get(row, 'Type', '') or '').strip() or None,
                    ball_in_court=str(safe_get(row, 'Ball In Court', '') or '').strip() or None,
                    submittal_manager=str(safe_get(row, 'Submittal Manager', '') or '').strip() or None
                )
                db.session.add(submittal)
                inserted_count += 1
            except Exception as exc:
                error_count += 1
                logger.error(f"Error processing row {idx}: {str(exc)}", exc_info=True)
                continue

        # Commit all inserts
        try:
            db.session.commit()
        except Exception as exc:
            logger.error(f"Error committing submittals: {str(exc)}", exc_info=True)
            db.session.rollback()
            return jsonify({'error': f'Failed to save submittals: {str(exc)}'}), 500

        # Assign order_number based on ball_in_court_due_date for submittals with null order_number
        # Group by ball_in_court, sort by ball_in_court_due_date (nulls last), then assign 0-x within each group
        try:
            submittals_without_order = ProcoreSubmittal.query.filter(
                ProcoreSubmittal.order_number.is_(None)
            ).all()
            
            # Group by ball_in_court
            grouped_by_ball_in_court = defaultdict(list)
            for submittal in submittals_without_order:
                ball_in_court_value = submittal.ball_in_court or 'None'
                grouped_by_ball_in_court[ball_in_court_value].append(submittal)
            
            # Sort each group by ball_in_court_due_date (nulls last) and assign order numbers
            total_assigned = 0
            for ball_in_court_value, submittals in grouped_by_ball_in_court.items():
                # Sort by ball_in_court_due_date (nulls last)
                submittals.sort(key=lambda s: (s.ball_in_court_due_date is None, s.ball_in_court_due_date or date.max))
                
                # Assign 0.0-x within this group (using floats)
                for index, submittal in enumerate(submittals):
                    submittal.order_number = float(index)
                    submittal.last_updated = datetime.utcnow()
                    total_assigned += 1
            
            db.session.commit()
        except Exception as exc:
            logger.error(f"Error assigning order numbers: {str(exc)}", exc_info=True)
            db.session.rollback()
            # Don't fail the whole request if order assignment fails

        return jsonify({
            'success': True, 
            'rows_updated': len(df), 
            'rows_inserted': inserted_count,
            'rows_skipped': skipped_count,
            'rows_with_errors': error_count,
            'projects_cached': len(project_id_cache), 
            'order_numbers_assigned': total_assigned
        }), 200

    except Exception as exc:
        logger.error(f"Unexpected error in drafting_workload_submittals: {str(exc)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'error': 'An unexpected error occurred',
            'details': str(exc)
        }), 500

@procore_bp.route("/api/drafting-work-load/order", methods=["PUT"])
def update_submittal_order():
    """Update the order_number for a submittal (simple update, no cascading)"""
    try:
        data = request.json
        submittal_id = data.get('submittal_id')
        order_number = data.get('order_number')
        
        if submittal_id is None:
            return jsonify({
                "error": "submittal_id is required"
            }), 400
        
        # Ensure submittal_id is a string for proper database comparison
        submittal_id = str(submittal_id)
        
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        # Convert order_number to float if provided, allow None
        if order_number is not None:
            try:
                order_number = float(order_number)
            except (ValueError, TypeError):
                return jsonify({
                    "error": "order_number must be a valid number"
                }), 400
        
        # Simple update - no cascading
        submittal.order_number = order_number
        submittal.last_updated = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "order_number": order_number
        }), 200
    except Exception as exc:
        logger.error("Error updating submittal order", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update order",
            "details": str(exc)
        }), 500