"""
Script to create Procore webhooks for Submittals updates and creates.

Usage:
    # Create webhooks for all projects in database
    python -m app.procore.scripts.create
    
    # Create webhook for a single project
    python -m app.procore.scripts.create --project-id <project_id> [--namespace <namespace>]

Scans the procore_submittals table for unique project_numbers,
creates webhooks for Submittals resource with 'update' and 'create' event types,
and logs all webhook responses to a file for debugging.
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


def create_webhook_and_trigger(procore_client, project_id: int, project_number: Optional[str], 
                               namespace: str = "mile-high-metal-works") -> Dict:
    """
    Create a webhook and triggers for Submittals updates and creates if they don't exist.
    Returns operation result dictionary.
    """
    log_file = "procore_webhook_responses.log"
    required_event_types = ["update", "create"]
    
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
                    trigger_response = procore_client.create_webhook_trigger(project_id, existing_hook_id, event_type)
                    log_operation(
                        log_file,
                        "create_webhook_trigger",
                        project_id,
                        project_number,
                        {"hook_id": existing_hook_id, "event_type": event_type, "response": trigger_response},
                        "success"
                    )
                    created_triggers.append(event_type)
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
                return {
                    "status": "partial_success",
                    "action": "some_triggers_created",
                    "hook_id": existing_hook_id,
                    "created_triggers": created_triggers,
                    "errors": trigger_errors
                }
            
            return {
                "status": "success",
                "action": "triggers_created",
                "hook_id": existing_hook_id,
                "created_triggers": created_triggers
            }
            
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
    
    # Create new webhook if none exists
    try:
        webhook_response = procore_client.create_project_webhook(project_id, "Submittals Updates", "update")
        
        # Handle Procore API response format
        print(f"DEBUG: Webhook creation response: {webhook_response}")
        
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
                hook_id = webhook_response.get("hook_id") or webhook_response.get("webhook_id")
            if isinstance(webhook_response, dict) and "data" in webhook_response:
                data = webhook_response["data"]
                if isinstance(data, dict):
                    hook_id = hook_id or data.get("hook_id") or data.get("webhook_id")
            
            if not hook_id:
                raise ValueError(f"Webhook created but no hook_id returned. Response keys: {list(webhook_response.keys()) if isinstance(webhook_response, dict) else 'not a dict'}. Full response: {webhook_response}")
        
        log_operation(
            log_file,
            "create_project_webhook",
            project_id,
            project_number,
            webhook_response,
            "success"
        )
        
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
            return {
                "status": "partial_success",
                "action": "webhook_created_some_triggers_failed",
                "hook_id": hook_id,
                "webhook_response": webhook_response,
                "created_triggers": created_triggers,
                "trigger_errors": trigger_errors
            }
        
        return {
            "status": "success",
            "action": "webhook_and_triggers_created",
            "hook_id": hook_id,
            "webhook_response": webhook_response,
            "created_triggers": created_triggers
        }
            
    except Exception as e:
        error_data = {"error": str(e)}
        log_operation(
            log_file,
            "create_project_webhook",
            project_id,
            project_number,
            error_data,
            "error"
        )
        return {
            "status": "error",
            "action": "create_webhook",
            "error": str(e)
        }


def create_single_webhook(project_id: int, namespace: str = "mile-high-metal-works"):
    """Create a webhook for a single project."""
    app = create_app()
    
    with app.app_context():
        procore_client = get_procore_client()
        
        print(f"Creating webhook for Project ID: {project_id}")
        print(f"Namespace: {namespace}")
        print("-" * 60)
        
        result = create_webhook_and_trigger(procore_client, project_id, None, namespace)
        
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Status: {result['status']}")
        if result.get("message"):
            print(f"Message: {result['message']}")
        if result.get("hook_id"):
            print(f"Webhook ID: {result['hook_id']}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        print(f"\nDetailed response logged to: logs/procore_webhook_responses.log")
        
        return result


def main():
    """Main function to create webhooks."""
    parser = argparse.ArgumentParser(
        description="Create Procore webhooks for Submittals updates and creates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create webhooks for all projects in database
  python -m app.procore.scripts.create
  
  # Create webhook for a specific project by ID
  python -m app.procore.scripts.create --project-id 12345
  
  # Create webhook with custom namespace
  python -m app.procore.scripts.create --project-id 12345 --namespace my-namespace
        """
    )
    
    parser.add_argument(
        "--project-id",
        type=int,
        help="Procore project ID to create webhook for (single webhook mode)"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="mile-high-metal-works",
        help="Webhook namespace (default: mile-high-metal-works)"
    )
    
    args = parser.parse_args()
    
    app = create_app()
    
    with app.app_context():
        # Single webhook mode
        if args.project_id:
            create_single_webhook(args.project_id, args.namespace)
            return
        
        # Batch mode: create webhooks for all projects in database
        print("Scanning procore_submittals table for unique projects...")
        projects = get_unique_projects()
        
        if not projects:
            print("No projects found in procore_submittals table.")
            return
        
        print(f"Found {len(projects)} unique project(s).")
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
        
        for project_id, project_number in projects:
            print(f"\nProcessing Project ID: {project_id} (Project Number: {project_number})")
            result = create_webhook_and_trigger(procore_client, project_id, project_number, namespace)
            results["details"].append({
                "project_id": project_id,
                "project_number": project_number,
                "result": result
            })
            
            if result["status"] == "success":
                results["success"] += 1
            elif result["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["error"] += 1
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total projects processed: {results['total']}")
        print(f"Webhooks/triggers created: {results['success']}")
        print(f"Already existed (skipped): {results['skipped']}")
        print(f"Errors: {results['error']}")
        print(f"\nDetailed responses logged to: logs/procore_webhook_responses.log")


if __name__ == "__main__":
    main()

