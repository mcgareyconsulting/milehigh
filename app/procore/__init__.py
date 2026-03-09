# Package
import os
import json
from datetime import datetime
from typing import Optional

from flask import Blueprint, request, jsonify, current_app
from app.models import db, Submittals

from app.procore.procore import (
    get_project_id_by_project_name,
    check_and_update_submittal,
    create_submittal_from_webhook,
    comprehensive_health_scan,
)

from app.procore.helpers import resolve_webhook_user_ids, is_duplicate_webhook, create_submittal_event as _create_submittal_event_helper

from app.logging_config import get_logger
from app.config import Config as cfg
from app.trello.context import sync_operation_context
from app.trello.logging import safe_log_sync_event

logger = get_logger(__name__)

procore_bp = Blueprint("procore", __name__)


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

        # Extract metadata (Procore webhook uses resource_id, project_id, reason, resource_type)
        resource_id_raw = payload.get("resource_id")
        project_id_raw = payload.get("project_id")
        event_type = payload.get("reason") or "unknown"
        resource_type = payload.get("resource_type") or "unknown"
        external_user_id, internal_user_id = resolve_webhook_user_ids(payload)
        if external_user_id is not None:
            current_app.logger.info(
                "Procore webhook user: external_user_id=%s, internal_user_id=%s",
                external_user_id, internal_user_id
            )
        current_app.logger.debug("Procore webhook payload: %s", json.dumps(payload) if payload else "{}")

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

        current_app.logger.info(
            "Received Procore webhook: resource=%s, event_type=%s, id=%s, project=%s",
            resource_type, event_type, resource_id, project_id
        )

        # Burst dedup: Procore sends 2-5 identical deliveries within ~7 seconds per update.
        # Write a receipt row for the first delivery in the 15s window; reject the rest.
        if is_duplicate_webhook(resource_id, project_id, event_type):
            current_app.logger.info(
                "Duplicate webhook delivery rejected (burst dedup): id=%s, event=%s",
                resource_id, event_type,
            )
            return jsonify({"status": "deduplicated"}), 200

        # Source attribution: if the webhook was triggered by the connector service account,
        # it's a bounce-back from our own Procore API call. Tag it as 'Connector' so it's
        # visible in history but filterable. Real user changes come with a different user_id.
        is_connector = (
            external_user_id is not None
            and str(external_user_id) == str(cfg.PROCORE_CONNECTOR_USER_ID)
        )
        event_source = 'Connector' if is_connector else 'Procore'
        if is_connector:
            current_app.logger.info(
                "Procore webhook from connector account (user %s); id=%s, project=%s — will process for side-effect diffs",
                external_user_id, resource_id, project_id,
            )

        # Process submittal create or update
        try:
            if event_type == "create":
                current_app.logger.info(
                    f"Processing create event for submittal {resource_id} in project {project_id}"
                )
                try:
                    created, record, error_msg = create_submittal_from_webhook(project_id, resource_id, webhook_payload=payload, source=event_source)
                    
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
                                    submittal_title=record.title if record else None,
                                    project_name=record.project_name if record else None
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
                old_record = Submittals.query.filter_by(submittal_id=str(resource_id)).first()
                
                # If record doesn't exist, try to create it (fallback for race conditions)
                # This handles the case where update events arrive before create events
                if not old_record:
                    current_app.logger.warning(
                        f"Update event received for submittal {resource_id} but record doesn't exist. "
                        f"Attempting to create it first (fallback for race conditions)..."
                    )
                    created, new_record, create_error = create_submittal_from_webhook(project_id, resource_id, webhook_payload=payload, source=event_source)
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
                old_title = old_record.title if old_record else None
                old_manager = old_record.submittal_manager if old_record else None
                
                ball_updated, status_updated, title_updated, manager_updated, record, ball_in_court, status = check_and_update_submittal(
                    project_id,
                    resource_id,
                    webhook_payload=payload,
                    source=event_source,
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
                                submittal_title=record.title if record else None,
                                project_name=record.project_name if record else None
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
                                submittal_title=record.title if record else None,
                                project_name=record.project_name if record else None
                            )
                
                # Log title changes
                if title_updated:
                    with sync_operation_context(
                        operation_type="procore_submittal_title",
                        source_system="procore",
                        source_id=str(resource_id)
                    ) as sync_op:
                        if sync_op:
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "INFO",
                                "Submittal title updated via webhook",
                                submittal_id=resource_id,
                                project_id=project_id,
                                old_value=old_title,
                                new_value=record.title if record else None,
                                submittal_title=record.title if record else None,
                                project_name=record.project_name if record else None
                            )
                
                # Log submittal manager changes
                if manager_updated:
                    with sync_operation_context(
                        operation_type="procore_submittal_manager",
                        source_system="procore",
                        source_id=str(resource_id)
                    ) as sync_op:
                        if sync_op:
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "INFO",
                                "Submittal manager updated via webhook",
                                submittal_id=resource_id,
                                project_id=project_id,
                                old_value=old_manager,
                                new_value=record.submittal_manager if record else None,
                                submittal_title=record.title if record else None,
                                project_name=record.project_name if record else None
                            )

                # Log when webhook resulted in no updates (DB already in sync)
                if not (ball_updated or status_updated or title_updated or manager_updated):
                    current_app.logger.info(
                        "Procore webhook update for submittal id=%s project=%s: no changes applied (DB already in sync, source=%s)",
                        resource_id, project_id, event_source,
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



@procore_bp.route("/health-scan", methods=["GET"])
def health_scan():
    """
    Run comprehensive health scan to find orphaned submittals and sync issues.
    Returns scan results without making any changes to the database.
    
    Returns:
        JSON response with:
            - summary: Summary statistics
            - differences: Detailed list of sync issues, deleted submittals, and errors
            - webhook_status: Webhook health for orphaned projects
    """
    try:
        logger.info("Starting comprehensive health scan via API")
        result = comprehensive_health_scan(skip_user_prompt=True)
        
        # Convert result to JSON-serializable format
        # Remove the user input prompt part since this is API-based
        response_data = {
            'summary': result['summary'],
            'differences': {
                'sync_issues': [
                    {
                        'submittal_id': issue['submittal_id'],
                        'project_id': issue['project_id'],
                        'project_name': issue['project_name'],
                        'title': issue['title'],
                        'ball_in_court': issue['ball_in_court'],
                        'status': issue['status'],
                        'recommendation': issue['recommendation']
                    }
                    for issue in result['differences']['sync_issues']
                ],
                'deleted_submittals': result['differences']['deleted_submittals'],
                'api_fetch_errors': result['differences']['api_fetch_errors']
            },
            'webhook_status': {
                'projects_with_webhooks': result['webhook_status']['projects_with_webhooks'] if result['webhook_status'] else [],
                'projects_without_webhooks': result['webhook_status']['projects_without_webhooks'] if result['webhook_status'] else [],
                'webhook_details': result['webhook_status']['webhook_details'] if result['webhook_status'] else {}
            } if result['webhook_status'] else None
        }
        
        return jsonify(response_data), 200
        
    except Exception as exc:
        logger.error(f"Error running health scan: {exc}", exc_info=True)
        return jsonify({
            "error": "Failed to run health scan",
            "details": str(exc)
        }), 500


@procore_bp.route("/health-scan/update", methods=["POST"])
def health_scan_update():
    """
    Update DB records to match API values for submittals with sync issues.
    Expects a list of submittal IDs to update in the request body.
    If no submittal_ids provided, updates all submittals with sync issues from the last scan.
    
    Request body (optional):
        {
            "submittal_ids": ["123", "456"]  // Optional: specific submittals to update
        }
    
    Returns:
        JSON response with update results
    """
    try:
        data = request.get_json() or {}
        submittal_ids = data.get('submittal_ids', [])
        
        # Run health scan to get current sync issues
        logger.info("Running health scan to identify sync issues for update")
        result = comprehensive_health_scan(skip_user_prompt=True)
        sync_issues = result['differences']['sync_issues']
        
        if not sync_issues:
            return jsonify({
                "success": True,
                "message": "No sync issues found - all records are up to date",
                "updated_count": 0
            }), 200
        
        # Filter to specific submittal_ids if provided
        if submittal_ids:
            sync_issues = [issue for issue in sync_issues if issue['submittal_id'] in submittal_ids]
            if not sync_issues:
                return jsonify({
                    "error": "No matching sync issues found for provided submittal_ids"
                }), 404
        
        updated_count = 0
        updated_submittals = []
        errors = []
        
        for issue in sync_issues:
            try:
                # Find the DB record
                db_record = Submittals.query.filter_by(submittal_id=issue['submittal_id']).first()
                if not db_record:
                    errors.append({
                        'submittal_id': issue['submittal_id'],
                        'error': 'DB record not found'
                    })
                    continue
                
                updates = {}
                
                # Update ball_in_court if there's a mismatch
                if issue['ball_in_court']['mismatch']:
                    old_value = db_record.ball_in_court
                    db_record.ball_in_court = issue['ball_in_court']['api']
                    updates['ball_in_court'] = {
                        'old': old_value,
                        'new': issue['ball_in_court']['api']
                    }
                
                # Update status if there's a mismatch
                if issue['status']['mismatch']:
                    old_value = db_record.status
                    db_record.status = issue['status']['api']
                    updates['status'] = {
                        'old': old_value,
                        'new': issue['status']['api']
                    }
                
                # Update last_updated timestamp
                db_record.last_updated = datetime.utcnow()
                
                # Create submittal event for update
                if updates:
                    try:
                        _create_submittal_event_helper(
                            issue['submittal_id'], "updated", updates.copy(),
                            source='HealthScan',
                        )
                    except Exception as event_error:
                        logger.warning(f"Failed to create SubmittalEvent for submittal {issue['submittal_id']} from health scan: {event_error}", exc_info=True)
                
                updated_submittals.append({
                    'submittal_id': issue['submittal_id'],
                    'project_id': issue['project_id'],
                    'title': issue['title'],
                    'updates': updates
                })
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Error updating submittal {issue['submittal_id']}: {e}")
                errors.append({
                    'submittal_id': issue['submittal_id'],
                    'error': str(e)
                })
        
        # Commit all changes
        try:
            db.session.commit()
            logger.info(f"Successfully updated {updated_count} submittal records in database")
            
            return jsonify({
                "success": True,
                "updated_count": updated_count,
                "updated_submittals": updated_submittals,
                "errors": errors
            }), 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error committing updates to database: {e}")
            return jsonify({
                "error": "Failed to commit updates to database",
                "details": str(e)
            }), 500
        
    except Exception as exc:
        logger.error(f"Error updating records from health scan: {exc}", exc_info=True)
        db.session.rollback()
        return jsonify({
            "error": "Failed to update records",
            "details": str(exc)
        }), 500


@procore_bp.route("/admin/verify-pin", methods=["POST"])
def verify_admin_pin():
    """
    Verify admin PIN for health scan admin page.
    
    Request body:
        {
            "pin": "1234"
        }
    
    Returns:
        JSON response with success status
    """
    try:
        data = request.get_json() or {}
        provided_pin = data.get('pin', '')
        correct_pin = cfg.ADMIN_PIN
        
        if provided_pin == correct_pin:
            return jsonify({
                "success": True,
                "message": "PIN verified"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Invalid PIN"
            }), 401
            
    except Exception as exc:
        logger.error(f"Error verifying admin PIN: {exc}", exc_info=True)
        return jsonify({
            "error": "Failed to verify PIN",
            "details": str(exc)
        }), 500