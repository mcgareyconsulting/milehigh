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

from app.procore.procore import get_project_id_by_project_name, check_and_update_submittal, create_submittal_from_webhook

from app.procore.helpers import clean_value

from app.logging_config import get_logger
from app.config import Config as cfg
from app.sync.context import sync_operation_context
from app.sync.logging import safe_log_sync_event

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
    Procore webhook endpoint to receive Submittals create and update events.
    Handles both 'create' and 'update' event types:
    - 'create': Creates a new submittal record in the database
    - 'update': Updates existing submittal record (ball_in_court, status, etc.)
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
        
        # Debug: Log the full payload for create events to verify structure
        if event_type == "create":
            current_app.logger.debug(
                f"DEBUG: Full webhook payload for create event: {json.dumps(payload)}"
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
            current_app.logger.debug(
                f"DEBUG: About to process event. event_type='{event_type}' "
                f"(type: {type(event_type)}), resource_id={resource_id}"
            )
            
            # Handle create events - add new submittal to database
            if event_type == "create":
                current_app.logger.info(
                    f"Processing create event for submittal {resource_id} in project {project_id}"
                )
                try:
                    created, record, error_msg = create_submittal_from_webhook(project_id, resource_id)
                    
                    if created and record:
                        with sync_operation_context(
                            operation_type="procore_submittal_create",
                            source_system="procore",
                            source_id=str(resource_id)
                        ) as sync_op:
                            if sync_op:
                                safe_log_sync_event(
                                    sync_op.operation_id,
                                    "INFO",
                                    "Submittal created via webhook",
                                    submittal_id=resource_id,
                                    project_id=project_id,
                                    submittal_title=record.title if record else None
                                )
                        current_app.logger.info(
                            f"✓ Successfully created new submittal {resource_id} from webhook create event"
                        )
                    elif error_msg:
                        current_app.logger.error(
                            f"✗ Failed to create submittal {resource_id}: {error_msg}",
                            exc_info=True
                        )
                    elif record:
                        current_app.logger.info(
                            f"Submittal {resource_id} already exists in database, skipped creation"
                        )
                    else:
                        # This case: created=False, record=None, error_msg=None
                        # Should not happen, but log it
                        current_app.logger.warning(
                            f"Create submittal returned unexpected state: created={created}, "
                            f"record={'exists' if record else 'None'}, error_msg={error_msg}"
                        )
                except Exception as create_exception:
                    current_app.logger.error(
                        f"✗ Exception while processing create event for submittal {resource_id}: {create_exception}",
                        exc_info=True
                    )
            
            # Handle update events - update existing submittal
            elif event_type == "update":
                # Check if record exists first
                old_record = ProcoreSubmittal.query.filter_by(submittal_id=str(resource_id)).first()
                
                # If record doesn't exist, try to create it (fallback for race conditions)
                # This handles the case where update events arrive before create events
                if not old_record:
                    current_app.logger.warning(
                        f"Update event received for submittal {resource_id} but record doesn't exist. "
                        f"Attempting to create it first (fallback for race conditions)..."
                    )
                    created, new_record, create_error = create_submittal_from_webhook(project_id, resource_id)
                    if created and new_record:
                        current_app.logger.info(
                            f"Successfully created missing submittal {resource_id} from update event fallback"
                        )
                        old_record = new_record
                    elif new_record:  # Record exists but wasn't newly created (already existed)
                        current_app.logger.info(
                            f"Submittal {resource_id} was already created by another process (likely create event), "
                            f"using existing record"
                        )
                        old_record = new_record
                    elif create_error:
                        current_app.logger.error(
                            f"Failed to create missing submittal {resource_id} from update event: {create_error}"
                        )
                
                old_ball_in_court = old_record.ball_in_court if old_record else None
                old_status = old_record.status if old_record else None
                
                ball_updated, status_updated, record, ball_in_court, status = check_and_update_submittal(
                    project_id, 
                    resource_id
                )
                
                # Log ball_in_court changes
                if ball_updated:
                    with sync_operation_context(
                        operation_type="procore_ball_in_court",
                        source_system="procore",
                        source_id=str(resource_id)
                    ) as sync_op:
                        if sync_op:
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "INFO",
                                "Ball in court updated via webhook",
                                submittal_id=resource_id,
                                project_id=project_id,
                                old_value=old_ball_in_court,
                                new_value=ball_in_court,
                                submittal_title=record.title if record else None
                            )
                
                # Log status changes
                if status_updated:
                    with sync_operation_context(
                        operation_type="procore_submittal_status",
                        source_system="procore",
                        source_id=str(resource_id)
                    ) as sync_op:
                        if sync_op:
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "INFO",
                                "Submittal status updated via webhook",
                                submittal_id=resource_id,
                                project_id=project_id,
                                old_value=old_status,
                                new_value=status,
                                submittal_title=record.title if record else None
                            )
            else:
                current_app.logger.warning(
                    f"Unhandled event type '{event_type}' for submittal {resource_id}, ignoring. "
                    f"Expected 'create' or 'update'"
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


@procore_bp.route("/api/webhook/test", methods=["HEAD", "POST"])
def webhook_test():
    """
    Testing endpoint to cleanly parse and display Procore webhook information.
    Useful for identifying new resources and understanding webhook payload structure.
    
    Returns a formatted JSON response with:
    - All headers received
    - Parsed payload structure
    - Identified resource information
    - All top-level and nested keys
    - Raw payload for reference
    """
    if request.method == "HEAD":
        # Procore webhook verification request
        return "", 200
    
    if request.method == "POST":
        try:
            # Get all headers
            headers = dict(request.headers)
            
            # Get payload
            try:
                payload = request.get_json(silent=True) or {}
            except Exception as e:
                payload = {"_parse_error": str(e)}
            
            # Extract common fields
            resource_id = payload.get("resource_id") or payload.get("id")
            project_id = payload.get("project_id")
            event_type = payload.get("reason") or payload.get("event_type")
            resource_type = payload.get("resource_type")
            
            # Recursively extract all keys from nested structures
            def extract_keys(obj, prefix="", max_depth=5, current_depth=0):
                """Recursively extract all keys from nested dict/list structures"""
                if current_depth >= max_depth:
                    return [f"{prefix}... (max depth reached)"]
                
                keys = []
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        full_key = f"{prefix}.{key}" if prefix else key
                        keys.append(full_key)
                        if isinstance(value, (dict, list)):
                            keys.extend(extract_keys(value, full_key, max_depth, current_depth + 1))
                elif isinstance(obj, list) and len(obj) > 0:
                    # Sample first item if it's a dict
                    if isinstance(obj[0], dict):
                        keys.append(f"{prefix}[0] (sample from list)")
                        keys.extend(extract_keys(obj[0], f"{prefix}[0]", max_depth, current_depth + 1))
                    else:
                        keys.append(f"{prefix}[] (list of {type(obj[0]).__name__})")
                return keys
            
            all_keys = extract_keys(payload)
            
            # Identify data types for each top-level key
            def get_value_info(value):
                """Get information about a value's type and structure"""
                if value is None:
                    return {"type": "null", "value": None}
                elif isinstance(value, dict):
                    return {
                        "type": "object",
                        "keys": list(value.keys()),
                        "key_count": len(value)
                    }
                elif isinstance(value, list):
                    return {
                        "type": "array",
                        "length": len(value),
                        "item_type": type(value[0]).__name__ if len(value) > 0 else "empty"
                    }
                elif isinstance(value, (str, int, float, bool)):
                    return {
                        "type": type(value).__name__,
                        "value": value if not isinstance(value, str) or len(value) < 200 else value[:200] + "..."
                    }
                else:
                    return {
                        "type": type(value).__name__,
                        "value": str(value)[:200]
                    }
            
            top_level_info = {
                key: get_value_info(value)
                for key, value in payload.items()
            }
            
            # Build response
            response = {
                "timestamp": datetime.utcnow().isoformat(),
                "summary": {
                    "resource_id": resource_id,
                    "project_id": project_id,
                    "event_type": event_type,
                    "resource_type": resource_type,
                    "payload_keys_count": len(payload),
                    "total_nested_keys": len(all_keys)
                },
                "headers": headers,
                "payload_structure": {
                    "top_level_keys": top_level_info,
                    "all_keys": sorted(set(all_keys))
                },
                "raw_payload": payload
            }
            
            # Log the parsed analysis to a separate test log file
            test_log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "headers": headers,
                "parsed_analysis": {
                    "summary": response["summary"],
                    "payload_structure": response["payload_structure"]
                },
                "raw_payload": payload
            }
            
            # Log to a separate test file for easy review
            webhook_logs_dir = cfg.SNAPSHOTS_DIR
            os.makedirs(webhook_logs_dir, exist_ok=True)
            test_log_path = os.path.join(webhook_logs_dir, "procore_webhook_test_analysis.log")
            
            try:
                with open(test_log_path, "a") as f:
                    f.write(json.dumps(test_log_entry) + "\n")
                logger.info(f"Logged webhook test analysis to {test_log_path}")
            except Exception as log_error:
                logger.error(f"Failed to log webhook test analysis: {str(log_error)}", exc_info=True)
            
            logger.info(
                f"Webhook test endpoint received: resource_type={resource_type}, "
                f"event_type={event_type}, resource_id={resource_id}, project_id={project_id}"
            )
            
            return jsonify(response), 200
            
        except Exception as e:
            logger.error(f"Error in webhook test endpoint: {str(e)}", exc_info=True)
            return jsonify({
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
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
    """Return Drafting Work Load data from the db, filtered to only show submittals with status='Open'"""
    # Filter to only show submittals with status == 'Open'
    # Exclude None statuses - only show submittals that are explicitly 'Open'
    submittals = ProcoreSubmittal.query.filter(
        ProcoreSubmittal.status == 'Open'
    ).all()
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

                # Get ball_in_court value and determine if it's multiple assignees
                ball_in_court_value = str(safe_get(row, 'Ball In Court', '') or '').strip() or None
                is_multiple_assignees = ball_in_court_value and ',' in ball_in_court_value
                
                # Insert/update in DB with cleaned values
                submittal = ProcoreSubmittal(
                    submittal_id=submittal_id,
                    procore_project_id=project_id,
                    project_number=str(safe_get(row, 'Project Number', '') or '').strip() or None,
                    project_name=project_name,
                    title=str(safe_get(row, 'Title', '') or '').strip() or None,
                    status=str(safe_get(row, 'Status', '') or '').strip() or None,
                    type=str(safe_get(row, 'Type', '') or '').strip() or None,
                    ball_in_court=ball_in_court_value,
                    submittal_manager=str(safe_get(row, 'Submittal Manager', '') or '').strip() or None,
                    was_multiple_assignees=is_multiple_assignees
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

        # Note: Order numbers are no longer auto-assigned.
        # Submittals start with NULL order_number and only get assigned via drag-and-drop or manual entry.

        return jsonify({
            'success': True, 
            'rows_updated': len(df), 
            'rows_inserted': inserted_count,
            'rows_skipped': skipped_count,
            'rows_with_errors': error_count,
            'projects_cached': len(project_id_cache)
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
                # Block 0 - order numbers must be > 0 or NULL
                if order_number == 0:
                    return jsonify({
                        "error": "order_number cannot be 0"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "error": "order_number must be a valid number"
                }), 400
        
        # If setting a number >= 1, renumber the entire ball_in_court group to be tight (1, 2, 3, ...)
        # while preserving decimals < 1 (urgent orders)
        if order_number is not None and order_number >= 1:
            ball_in_court = submittal.ball_in_court
            if ball_in_court:
                # Get all submittals in the same ball_in_court group
                same_group = ProcoreSubmittal.query.filter_by(ball_in_court=ball_in_court).all()
                
                # Separate urgent (decimals < 1) from regular (>= 1 or NULL)
                urgent_rows = []
                regular_rows = []
                for s in same_group:
                    if s.submittal_id == submittal_id:
                        continue  # Skip the one we're updating
                    if s.order_number is not None and 0 < s.order_number < 1:
                        urgent_rows.append(s)
                    else:
                        regular_rows.append(s)
                
                # Sort urgent rows by order number
                urgent_rows.sort(key=lambda s: s.order_number)
                
                # Sort regular rows: those with order >= 1 first (by order), then NULLs (by last_updated, oldest first)
                regular_with_order = [s for s in regular_rows if s.order_number is not None and s.order_number >= 1]
                regular_with_order.sort(key=lambda s: s.order_number)
                regular_nulls = [s for s in regular_rows if s.order_number is None]
                regular_nulls.sort(key=lambda s: s.last_updated or datetime(1970, 1, 1))
                
                # The entered number represents desired position in the ordered section (1-based, after urgent)
                # So position 1 = first item after urgent decimals
                target_pos_in_ordered = int(order_number) - 1  # Convert to 0-based
                target_pos_in_ordered = max(0, min(target_pos_in_ordered, len(regular_with_order) + len(regular_nulls)))
                
                # Combine regular rows and insert submittal at target position
                all_regular = regular_with_order + regular_nulls
                reordered_regular = all_regular[:target_pos_in_ordered] + [submittal] + all_regular[target_pos_in_ordered:]
                
                # Final order: urgent first, then reordered regular
                final_order = urgent_rows + reordered_regular
                
                # Renumber: preserve urgent decimals, then number 1, 2, 3, ...
                next_integer = 1
                for row in final_order:
                    if row.order_number is not None and 0 < row.order_number < 1:
                        # Preserve urgent decimal - don't update
                        continue
                    else:
                        # Assign next integer
                        if row.order_number != next_integer:
                            row.order_number = float(next_integer)
                            row.last_updated = datetime.utcnow()
                        next_integer += 1
            else:
                # No ball_in_court, just update this one
                submittal.order_number = order_number
                submittal.last_updated = datetime.utcnow()
        else:
            # Setting to NULL or decimal < 1, just update this one (no renumbering)
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

@procore_bp.route("/api/drafting-work-load/submittal-drafting-status", methods=["PUT"])
def update_submittal_drafting_status():
    """Update the submittal_drafting_status for a submittal"""
    try:
        data = request.json
        submittal_id = data.get('submittal_id')
        submittal_drafting_status = data.get('submittal_drafting_status')
        
        if submittal_id is None:
            return jsonify({
                "error": "submittal_id is required"
            }), 400
        
        # Allow None or empty string for blank status
        if submittal_drafting_status is None:
            submittal_drafting_status = ''
        
        # Validate status value (empty string is allowed for blank/placeholder)
        valid_statuses = ['', 'STARTED', 'NEED VIF', 'HOLD']
        if submittal_drafting_status not in valid_statuses:
            return jsonify({
                "error": f"submittal_drafting_status must be one of: (blank), {', '.join([s for s in valid_statuses if s])}"
            }), 400
        
        # Ensure submittal_id is a string for proper database comparison
        submittal_id = str(submittal_id)
        
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        submittal.submittal_drafting_status = submittal_drafting_status
        submittal.last_updated = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "submittal_drafting_status": submittal_drafting_status
        }), 200
    except Exception as exc:
        logger.error("Error updating submittal drafting status", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update submittal_drafting_status",
            "details": str(exc)
        }), 500