"""
Script to ensure all projects in procore_submittals have webhooks with both
'update' and 'create' triggers for Submittals.

Usage:
    # Ensure webhooks for all projects in database
    python -m app.procore.scripts.ensure_webhooks
    
    # Ensure webhook for a single project
    python -m app.procore.scripts.ensure_webhooks --project-id <project_id>
    
    # Dry-run mode (report only, no changes)
    python -m app.procore.scripts.ensure_webhooks --dry-run

This script will:
1. Check each project in procore_submittals table
2. If webhook exists: verify it has both 'update' and 'create' triggers, add missing ones
3. If webhook doesn't exist: create webhook with both triggers
4. Report what actions were taken

Note: Triggers are independent of webhooks, so we add missing triggers to
existing webhooks rather than deleting and recreating them.
"""

import argparse
from typing import Dict, Optional

from app import create_app
from app.procore.client import get_procore_client
from app.procore.webhook_utils import (
    get_unique_projects,
    log_operation,
    get_webhook_triggers
)


def get_database_info(app) -> str:
    """Get database connection info for debugging (sanitized)."""
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "unknown")
    
    # Sanitize the URI to hide sensitive info but show enough to identify the database
    if db_uri.startswith("sqlite"):
        # SQLite - show the path
        return f"SQLite: {db_uri}"
    elif db_uri.startswith("postgresql"):
        # PostgreSQL - parse and show host/database name
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_uri)
            host = parsed.hostname or "unknown"
            port = f":{parsed.port}" if parsed.port else ""
            database = parsed.path.lstrip("/") if parsed.path else "unknown"
            return f"PostgreSQL: {host}{port}/{database}"
        except Exception:
            return f"PostgreSQL: {db_uri.split('@')[1] if '@' in db_uri else 'unknown'}"
    elif db_uri.startswith("mysql"):
        # MySQL - parse and show host/database name
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_uri)
            host = parsed.hostname or "unknown"
            port = f":{parsed.port}" if parsed.port else ""
            database = parsed.path.lstrip("/") if parsed.path else "unknown"
            return f"MySQL: {host}{port}/{database}"
        except Exception:
            return f"MySQL: {db_uri.split('@')[1] if '@' in db_uri else 'unknown'}"
    else:
        # Unknown format - show first part only
        return f"Database: {db_uri.split('://')[0] if '://' in db_uri else 'unknown'}"


def ensure_project_webhooks(procore_client, project_id: int, project_number: Optional[str],
                           namespace: str = "mile-high-metal-works", 
                           dry_run: bool = False) -> Dict:
    """
    Ensure a project has a webhook with both 'update' and 'create' triggers.
    If webhook exists, adds missing triggers. If not, creates webhook with both triggers.
    Returns operation result dictionary.
    """
    log_file = "procore_webhook_responses.log"
    required_event_types = ["update", "create"]
    
    result = {
        "project_id": project_id,
        "project_number": project_number,
        "status": "unknown",
        "actions_taken": [],
        "hook_id": None
    }
    
    try:
        # Get existing webhooks for this namespace
        try:
            webhooks = procore_client.list_project_webhooks(project_id, namespace)
            existing_hook_id = webhooks[0].get("id") if webhooks else None
        except Exception as e:
            log_operation(
                log_file,
                "list_webhooks_error",
                project_id,
                project_number,
                {"error": str(e)},
                "error"
            )
            existing_hook_id = None
            webhooks = []
        
        # If webhook exists, check and create missing triggers
        if existing_hook_id:
            if dry_run:
                # In dry-run, check what triggers exist but don't modify
                try:
                    triggers = get_webhook_triggers(procore_client, project_id, existing_hook_id)
                    existing_triggers = set()
                    for trigger in triggers:
                        if isinstance(trigger, dict):
                            resource = trigger.get("resource_name")
                            event_type = trigger.get("event_type")
                            if resource == "Submittals" and event_type in required_event_types:
                                existing_triggers.add(event_type)
                    
                    missing_triggers = [et for et in required_event_types if et not in existing_triggers]
                    if missing_triggers:
                        result["status"] = "dry_run"
                        result["message"] = f"Would add missing triggers: {', '.join(missing_triggers)}"
                        result["hook_id"] = existing_hook_id
                        result["existing_triggers"] = list(existing_triggers)
                        result["missing_triggers"] = missing_triggers
                    else:
                        result["status"] = "dry_run"
                        result["message"] = "Webhook already has both triggers (no changes needed)"
                        result["hook_id"] = existing_hook_id
                        result["existing_triggers"] = list(existing_triggers)
                except Exception as e:
                    result["status"] = "dry_run"
                    result["message"] = f"Would create new webhook (error checking existing: {str(e)})"
                return result
            
            try:
                triggers = get_webhook_triggers(procore_client, project_id, existing_hook_id)
                
                # Check which triggers already exist
                existing_triggers = set()
                for trigger in triggers:
                    if isinstance(trigger, dict):
                        resource = trigger.get("resource_name")
                        event_type = trigger.get("event_type")
                        if resource == "Submittals" and event_type in required_event_types:
                            existing_triggers.add(event_type)
                
                # Determine which triggers need to be created
                missing_triggers = [et for et in required_event_types if et not in existing_triggers]
                
                if not missing_triggers:
                    # All triggers already exist
                    log_operation(
                        log_file,
                        "webhook_triggers_complete",
                        project_id,
                        project_number,
                        {"hook_id": existing_hook_id, "triggers": list(existing_triggers)},
                        "skipped"
                    )
                    return {
                        "status": "skipped",
                        "message": "Webhook with all required triggers already exists",
                        "hook_id": existing_hook_id,
                        "existing_triggers": list(existing_triggers)
                    }
                
                # Create missing triggers
                created_triggers = []
                trigger_errors = []
                
                for event_type in missing_triggers:
                    try:
                        trigger_response = procore_client.create_webhook_trigger(
                            project_id, existing_hook_id, event_type
                        )
                        log_operation(
                            log_file,
                            "create_webhook_trigger",
                            project_id,
                            project_number,
                            {"hook_id": existing_hook_id, "event_type": event_type, "response": trigger_response},
                            "success"
                        )
                        created_triggers.append(event_type)
                        result["actions_taken"].append(f"trigger_created: {event_type}")
                    except Exception as e:
                        error_msg = str(e)
                        log_operation(
                            log_file,
                            "create_webhook_trigger",
                            project_id,
                            project_number,
                            {"hook_id": existing_hook_id, "event_type": event_type, "error": error_msg},
                            "error"
                        )
                        trigger_errors.append({"event_type": event_type, "error": error_msg})
                
                if trigger_errors:
                    result["status"] = "partial_success"
                    result["hook_id"] = existing_hook_id
                    result["created_triggers"] = created_triggers
                    result["trigger_errors"] = trigger_errors
                    result["message"] = f"Some triggers created, but some failed: {[e['event_type'] for e in trigger_errors]}"
                    return result
                
                result["status"] = "success"
                result["hook_id"] = existing_hook_id
                result["created_triggers"] = created_triggers
                result["message"] = f"Added missing triggers: {', '.join(created_triggers)}"
                return result
                
            except Exception as e:
                error_data = {"hook_id": existing_hook_id, "error": str(e)}
                log_operation(
                    log_file,
                    "check_triggers_error",
                    project_id,
                    project_number,
                    error_data,
                    "error"
                )
                # Fall through to create new webhook
        
        # Create new webhook if none exists (or if checking triggers failed)
        if dry_run:
            result["status"] = "dry_run"
            result["message"] = f"Would create new webhook with triggers: {', '.join(required_event_types)}"
            return result
        
        try:
            webhook_response = procore_client.create_project_webhook(project_id, "Submittals Updates", "update")
            
            # Extract hook_id from response
            if isinstance(webhook_response, dict) and "data" in webhook_response:
                webhook_data = webhook_response["data"]
                if isinstance(webhook_data, dict):
                    hook_id = webhook_data.get("id")
                else:
                    hook_id = None
            elif isinstance(webhook_response, dict):
                hook_id = webhook_response.get("id")
            else:
                hook_id = None
            
            if not hook_id:
                # Try alternative field names
                if isinstance(webhook_response, dict):
                    hook_id = (webhook_response.get("hook_id") or 
                              webhook_response.get("webhook_id"))
                if isinstance(webhook_response, dict) and "data" in webhook_response:
                    data = webhook_response["data"]
                    if isinstance(data, dict):
                        hook_id = (hook_id or 
                                  data.get("hook_id") or 
                                  data.get("webhook_id"))
            
            if not hook_id:
                raise ValueError(
                    f"Webhook created but no hook_id returned. Response keys: "
                    f"{list(webhook_response.keys()) if isinstance(webhook_response, dict) else 'not a dict'}. "
                    f"Full response: {webhook_response}"
                )
            
            log_operation(
                log_file,
                "create_project_webhook",
                project_id,
                project_number,
                {"hook_id": hook_id, "response": webhook_response},
                "success"
            )
            
            result["hook_id"] = hook_id
            result["actions_taken"].append("webhook_created")
            
            # Create triggers for both 'update' and 'create' events
            created_triggers = []
            trigger_errors = []
            
            for event_type in required_event_types:
                try:
                    trigger_response = procore_client.create_webhook_trigger(project_id, hook_id, event_type)
                    log_operation(
                        log_file,
                        "create_webhook_trigger",
                        project_id,
                        project_number,
                        {"hook_id": hook_id, "event_type": event_type, "response": trigger_response},
                        "success"
                    )
                    created_triggers.append(event_type)
                    result["actions_taken"].append(f"trigger_created: {event_type}")
                except Exception as e:
                    error_msg = str(e)
                    log_operation(
                        log_file,
                        "create_webhook_trigger",
                        project_id,
                        project_number,
                        {"hook_id": hook_id, "event_type": event_type, "error": error_msg},
                        "error"
                    )
                    trigger_errors.append({"event_type": event_type, "error": error_msg})
            
            if trigger_errors:
                result["status"] = "partial_success"
                result["created_triggers"] = created_triggers
                result["trigger_errors"] = trigger_errors
                result["message"] = f"Webhook created, but some triggers failed: {[e['event_type'] for e in trigger_errors]}"
            else:
                result["status"] = "success"
                result["created_triggers"] = created_triggers
                result["message"] = f"Webhook created with triggers: {', '.join(created_triggers)}"
            
            return result
                
        except Exception as e:
            error_msg = str(e)
            log_operation(
                log_file,
                "create_project_webhook",
                project_id,
                project_number,
                {"error": error_msg},
                "error"
            )
            result["status"] = "error"
            result["error"] = error_msg
            return result
        
    except Exception as e:
        error_msg = str(e)
        log_operation(
            log_file,
            "ensure_webhooks",
            project_id,
            project_number,
            {"error": error_msg},
            "error"
        )
        result["status"] = "error"
        result["error"] = error_msg
        return result


def ensure_single_webhook(project_id: int, namespace: str = "mile-high-metal-works",
                         dry_run: bool = False):
    """Ensure webhook for a single project."""
    app = create_app()
    
    with app.app_context():
        # Display database connection info for debugging
        db_info = get_database_info(app)
        print("=" * 60)
        print(f"DEBUG: Connected to database: {db_info}")
        print("=" * 60)
        print()
        
        procore_client = get_procore_client()
        
        print(f"{'[DRY RUN] ' if dry_run else ''}Ensuring webhook for Project ID: {project_id}")
        print(f"Namespace: {namespace}")
        print("-" * 60)
        
        result = ensure_project_webhooks(procore_client, project_id, None, namespace, dry_run)
        
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Status: {result['status']}")
        if result.get("message"):
            print(f"Message: {result['message']}")
        if result.get("hook_id"):
            print(f"Webhook ID: {result['hook_id']}")
        if result.get("actions_taken"):
            print(f"Actions: {', '.join(result['actions_taken'])}")
        if result.get("existing_triggers"):
            print(f"Existing triggers: {', '.join(result['existing_triggers'])}")
        if result.get("missing_triggers"):
            print(f"Missing triggers: {', '.join(result['missing_triggers'])}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        if not dry_run:
            print(f"\nDetailed response logged to: logs/procore_webhook_responses.log")
        
        return result


def main():
    """Main function to ensure webhooks for all projects."""
    parser = argparse.ArgumentParser(
        description="Ensure Procore webhooks with both update and create triggers for all projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ensure webhooks for all projects in database
  python -m app.procore.scripts.ensure_webhooks
  
  # Ensure webhook for a specific project by ID
  python -m app.procore.scripts.ensure_webhooks --project-id 12345
  
  # Dry-run mode (report only, no changes)
  python -m app.procore.scripts.ensure_webhooks --dry-run
  
  # Dry-run for a single project
  python -m app.procore.scripts.ensure_webhooks --project-id 12345 --dry-run
        """
    )
    
    parser.add_argument(
        "--project-id",
        type=int,
        help="Procore project ID to ensure webhook for (single project mode)"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="mile-high-metal-works",
        help="Webhook namespace (default: mile-high-metal-works)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    app = create_app()
    
    with app.app_context():
        # Display database connection info for debugging
        db_info = get_database_info(app)
        print("=" * 60)
        print(f"DEBUG: Connected to database: {db_info}")
        print("=" * 60)
        print()
        # Single project mode
        if args.project_id:
            ensure_single_webhook(args.project_id, args.namespace, args.dry_run)
            return
        
        # Batch mode: ensure webhooks for all projects in database
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Scanning procore_submittals table for unique projects...")
        projects = get_unique_projects(include_name=True)
        
        if not projects:
            print("No projects found in procore_submittals table.")
            return
        
        print(f"Found {len(projects)} unique project(s).")
        if args.dry_run:
            print("DRY RUN MODE: No changes will be made.")
        print("-" * 60)
        
        procore_client = get_procore_client()
        namespace = args.namespace
        
        results = {
            "total": len(projects),
            "success": 0,
            "skipped": 0,
            "error": 0,
            "details": []
        }
        
        for project_tuple in projects:
            if len(project_tuple) == 3:
                project_id, project_number, project_name = project_tuple
            else:
                project_id, project_number = project_tuple
                project_name = None
            
            print(f"\nProcessing Project ID: {project_id} (Project Number: {project_number})")
            
            result = ensure_project_webhooks(
                procore_client, project_id, project_number, namespace, args.dry_run
            )
            results["details"].append({
                "project_id": project_id,
                "project_number": project_number,
                "result": result
            })
            
            if result["status"] == "success":
                results["success"] += 1
            elif result["status"] == "skipped":
                results["skipped"] += 1
            elif result["status"] == "partial_success":
                # Count partial success as success (webhook created, some triggers may have failed)
                results["success"] += 1
            elif result["status"] == "dry_run":
                # In dry-run, don't count anything
                pass
            else:
                results["error"] += 1
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total projects processed: {results['total']}")
        if args.dry_run:
            print(f"[DRY RUN] No changes were made. Run without --dry-run to apply changes.")
        else:
            print(f"Webhooks/triggers created: {results['success']}")
            print(f"Already existed (skipped): {results['skipped']}")
            print(f"Errors: {results['error']}")
            print()
            
            # Show detailed breakdown by status
            successful_projects = []
            skipped_projects = []
            error_projects = []
            
            for detail in results["details"]:
                result_data = detail["result"]
                project_id = detail["project_id"]
                project_number = detail.get("project_number", "N/A")
                status = result_data.get("status", "unknown")
                
                if status == "success":
                    msg = result_data.get("message", "Success")
                    successful_projects.append(f"  - Project {project_id} ({project_number}): {msg}")
                elif status == "skipped":
                    skipped_projects.append(f"  - Project {project_id} ({project_number}): {result_data.get('message', 'Skipped')}")
                elif status == "partial_success":
                    msg = result_data.get("message", "Partial success")
                    successful_projects.append(f"  - Project {project_id} ({project_number}): {msg}")
                elif status == "error":
                    error_msg = result_data.get("error", "Unknown error")
                    error_projects.append(f"  - Project {project_id} ({project_number}): {error_msg}")
            
            if successful_projects:
                print(f"Projects with webhooks/triggers created ({len(successful_projects)}):")
                for proj in successful_projects:
                    print(proj)
                print()
            
            if skipped_projects:
                print(f"Projects already complete (skipped) ({len(skipped_projects)}):")
                for proj in skipped_projects:
                    print(proj)
                print()
            
            if error_projects:
                print(f"Projects with errors ({len(error_projects)}):")
                for proj in error_projects:
                    print(proj)
                print()
            
            print(f"Detailed responses logged to: logs/procore_webhook_responses.log")


if __name__ == "__main__":
    main()
