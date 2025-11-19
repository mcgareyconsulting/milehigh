# Package
import os
import json
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict
from typing import Optional

import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from app.models import db, ProcoreSubmittal, ProcoreWebhookEvents

from app.procore.procore import get_project_id_by_project_name, check_and_update_ball_in_court
from app import socketio

from app.procore.helpers import clean_value

from app.logging_config import get_logger
from app.config import Config as cfg

logger = get_logger(__name__)

procore_bp = Blueprint("procore", __name__)


def log_webhook_payload(payload: dict, headers: dict = None, hook_id: Optional[int] = None):
    """
    Log incoming webhook payload to persistent disk (same as Excel snapshots).
    Uses JSON Lines format (one JSON object per line) for easy parsing.
    
    Note: Procore webhook payloads don't include hook_id - it must be inferred
    by querying Procore's API or looking up webhooks for the project.
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "headers": dict(headers) if headers else {},
        "payload": payload,
        "hook_id": hook_id  # Will be None if not provided - must be looked up separately
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

DEBOUNCE_SECONDS = 8  # 8 seconds


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
            payload = request.get_json(silent=True) or {}
        except:
            payload = {}

        # Extract metadata
        # Procore webhook uses "id" for resource_id, not "resource_id"
        resource_id_raw = payload.get("resource_id")
        project_id_raw = payload.get("project_id")
        event_type = payload.get("reason") or "unknown"
        resource_type = payload.get("resource_type") or "unknown"

        # Validate and convert to int
        if not resource_id_raw:
            current_app.logger.warning("Webhook payload missing 'id' or 'resource_id'")
            return jsonify({"status": "ignored"}), 200
        
        try:
            resource_id = int(resource_id_raw)
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid resource_id format: {resource_id_raw}")
            return jsonify({"status": "ignored"}), 200
        
        if not project_id_raw:
            current_app.logger.warning("Webhook payload missing 'project_id'")
            return jsonify({"status": "ignored"}), 200
        
        try:
            project_id = int(project_id_raw)
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid project_id format: {project_id_raw}")
            return jsonify({"status": "ignored"}), 200

        # Use your existing logger setup
        current_app.logger.info(
            f"Received Procore webhook: resource={resource_type}, "
            f"event_type={event_type}, id={resource_id}, project={project_id}"
        )

        now = datetime.utcnow()

        # -----------------------------------
        # Debounce lookup
        # -----------------------------------
        event = ProcoreWebhookEvents.query.filter_by(
            resource_id=resource_id,
            project_id=project_id
        ).first()

        if event:
            diff = (now - event.last_seen).total_seconds()

            if diff < DEBOUNCE_SECONDS:
                current_app.logger.info(
                    f"Debounced duplicate webhook; id={resource_id}, "
                    f"project={project_id}, seen {diff:.2f}s ago"
                )
                # Update timestamp so rapid bursts extend window
                event.last_seen = now
                db.session.commit()
                return jsonify({"status": "debounced"}), 200

            # Not debounced → update timestamp
            event.last_seen = now

        else:
            # First time this resource/project combo has been seen
            event = ProcoreWebhookEvents(
                resource_id=resource_id,
                project_id=project_id,
                last_seen=now
            )
            db.session.add(event)
        db.session.commit()

        # -----------------------------------
        # PROCESS ACTUAL SUBMITTAL
        # -----------------------------------
        try:
            updated, record, ball_in_court = check_and_update_ball_in_court(
                project_id, 
                resource_id, 
                socketio_instance=socketio
            )
            if updated:
                current_app.logger.info(
                    f"Submittal {resource_id} ball_in_court updated via webhook"
                )
        except Exception as e:
            current_app.logger.error(
                f"Error processing submittal {resource_id}: {e}",
                exc_info=True
            )

        return jsonify({"status": "processed"}), 200

@procore_bp.route("/api/webhook/deliveries", methods=["GET"])
def webhook_deliveries():
    """
    API endpoint to get webhook deliveries from Procore's API.
    Takes company_id and project_id, looks up the webhook (assumes 1 webhook),
    and returns deliveries for that webhook.
    
    Query Parameters:
    - company_id: Company ID (required)
    - project_id: Project ID (required)
    - limit: Number of deliveries to return (default: 50, max: 200)
    
    Example:
    GET /procore/api/webhook/deliveries?company_id=18521&project_id=3260690
    GET /procore/api/webhook/deliveries?company_id=18521&project_id=3260690&limit=100
    """
    try:
        from app.procore.client import get_procore_client
        
        # Get query parameters
        company_id = request.args.get("company_id", type=int)
        project_id = request.args.get("project_id", type=int)
        limit = request.args.get("limit", default=50, type=int)
        limit = min(limit, 200)  # Cap at 200 for performance
        
        if not company_id or not project_id:
            return jsonify({
                "status": "error",
                "error": "company_id and project_id are required"
            }), 400
        
        # Get Procore client
        procore_client = get_procore_client()
        namespace = "mile-high-metal-works"
        
        # Look up webhooks for this project
        webhooks = procore_client.list_project_webhooks(project_id, namespace)
        
        if not webhooks or len(webhooks) == 0:
            return jsonify({
                "status": "success",
                "message": "No webhooks found for this project",
                "deliveries": [],
                "total": 0,
                "company_id": company_id,
                "project_id": project_id
            }), 200
        
        if len(webhooks) > 1:
            return jsonify({
                "status": "error",
                "error": f"Multiple webhooks found for project {project_id}. Cannot determine which one to use.",
                "webhook_count": len(webhooks),
                "webhook_ids": [w.get("id") for w in webhooks]
            }), 400
        
        # Get the single webhook
        hook_id = webhooks[0].get("id")
        if not hook_id:
            return jsonify({
                "status": "error",
                "error": "Webhook found but no hook_id in response"
            }), 500
        
        # Get deliveries for this webhook
        try:
            deliveries = procore_client.get_webhook_deliveries(company_id, project_id, hook_id)
            
            # Sort by most recent first
            if deliveries:
                deliveries.sort(
                    key=lambda x: x.get("created_at", ""), 
                    reverse=True
                )
                deliveries = deliveries[:limit]
            
            return jsonify({
                "status": "success",
                "deliveries": deliveries,
                "total": len(deliveries),
                "limit": limit,
                "company_id": company_id,
                "project_id": project_id,
                "hook_id": hook_id
            }), 200
            
        except Exception as e:
            logger.error(f"Error getting webhook deliveries: {str(e)}", exc_info=True)
            return jsonify({
                "status": "error",
                "error": str(e),
                "company_id": company_id,
                "project_id": project_id,
                "hook_id": hook_id
            }), 500
        
    except Exception as e:
        logger.error(f"Error retrieving webhook deliveries: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


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
                
                # Apply filters (Procore payload uses "resource_type" and "reason")
                if project_id_filter:
                    payload_project_id = payload_data.get("project_id") or payload_data.get("project", {}).get("id")
                    if str(payload_project_id) != str(project_id_filter):
                        continue
                
                if resource_name_filter:
                    # Procore uses "resource_type" in payload
                    payload_resource = payload_data.get("resource_type") or payload_data.get("resource_name") or payload_data.get("resource", {}).get("name")
                    if payload_resource != resource_name_filter:
                        continue
                
                if event_type_filter:
                    # Procore uses "reason" in payload for event type
                    payload_event = payload_data.get("reason") or payload_data.get("event_type") or payload_data.get("event", {}).get("type")
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
                          'Status', 'Type', 'Ball In Court', 
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

        # Assign order_number for submittals with null order_number
        # Group by ball_in_court, then assign 0-x within each group
        try:
            submittals_without_order = ProcoreSubmittal.query.filter(
                ProcoreSubmittal.order_number.is_(None)
            ).all()
            
            # Group by ball_in_court
            grouped_by_ball_in_court = defaultdict(list)
            for submittal in submittals_without_order:
                ball_in_court_value = submittal.ball_in_court or 'None'
                grouped_by_ball_in_court[ball_in_court_value].append(submittal)
            
            # Assign order numbers within each group
            total_assigned = 0
            for ball_in_court_value, submittals in grouped_by_ball_in_court.items():
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

@procore_bp.route("/api/drafting-work-load/notes", methods=["PUT"])
def update_submittal_notes():
    """Update the notes for a submittal"""
    try:
        data = request.json
        submittal_id = data.get('submittal_id')
        notes = data.get('notes')
        
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
        
        # Allow notes to be None or empty string
        if notes is not None:
            notes = str(notes).strip() or None
        
        submittal.notes = notes
        submittal.last_updated = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "notes": notes
        }), 200
    except Exception as exc:
        logger.error("Error updating submittal notes", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update notes",
            "details": str(exc)
        }), 500