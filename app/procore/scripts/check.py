"""
Script to check Procore webhook status for all projects in procore_submittals.

Usage:
    python -m app.procore.scripts.check

Lists all webhooks, their triggers, and delivery status to verify everything
is working correctly in production.
"""

import json
import os
from typing import List, Dict, Optional

from app import create_app
from app.procore.client import get_procore_client
from app.procore.webhook_utils import get_unique_projects, get_webhook_triggers
from app.config import Config as cfg


def check_project_webhooks(procore_client, project_id: int, project_number: Optional[str], 
                          project_name: Optional[str], namespace: str = "mile-high-metal-works") -> Dict:
    """Check webhook status for a specific project."""
    result = {
        "project_id": project_id,
        "project_number": project_number,
        "project_name": project_name,
        "webhooks": [],
        "status": "error"
    }
    
    try:
        # List all webhooks for this project
        webhooks = procore_client.list_project_webhooks(project_id, namespace)
        
        # Check if webhooks is a valid list
        if webhooks is None:
            result["status"] = "no_webhooks"
            return result
        
        if not isinstance(webhooks, list):
            result["error"] = f"Unexpected response type: {type(webhooks).__name__}, value: {webhooks}"
            result["status"] = "error"
            return result
        
        if not webhooks:
            result["status"] = "no_webhooks"
            return result
        
        # Check each webhook
        for webhook in webhooks:
            # Ensure webhook is a dictionary
            if not isinstance(webhook, dict):
                result["webhooks"].append({
                    "error": f"Unexpected webhook type: {type(webhook).__name__}",
                    "raw_value": str(webhook)[:200]  # Truncate for safety
                })
                continue
            
            hook_id = webhook.get("id")
            hook_info = {
                "hook_id": hook_id,
                "destination_url": webhook.get("destination_url"),
                "namespace": webhook.get("namespace"),
                "payload_version": webhook.get("payload_version"),
                "created_at": webhook.get("created_at"),
                "updated_at": webhook.get("updated_at"),
                "triggers": [],
                "deliveries": []
            }
            
            # Get triggers for this webhook
            try:
                triggers = get_webhook_triggers(procore_client, project_id, hook_id)
                if triggers:
                    # Ensure triggers is a list
                    if isinstance(triggers, list):
                        hook_info["triggers"] = triggers
                        
                        # Check if Submittals/update trigger exists
                        has_submittals_update = any(
                            isinstance(t, dict) and t.get("resource_name") == "Submittals" and t.get("event_type") == "update"
                            for t in triggers
                        )
                        hook_info["has_submittals_update"] = has_submittals_update
                    else:
                        hook_info["trigger_error"] = f"Unexpected triggers type: {type(triggers).__name__}"
            except Exception as e:
                hook_info["trigger_error"] = str(e)
            
            # Get recent deliveries (last 10) to check webhook activity
            try:
                deliveries = procore_client.get_webhook_deliveries(
                    cfg.PROD_PROCORE_COMPANY_ID, project_id, hook_id
                )
                if deliveries:
                    # Ensure deliveries is a list
                    if isinstance(deliveries, list):
                        # Sort by most recent and take last 10
                        hook_info["deliveries"] = sorted(
                            deliveries[:10], 
                            key=lambda x: x.get("created_at", "") if isinstance(x, dict) else "", 
                            reverse=True
                        )
                        hook_info["total_deliveries"] = len(deliveries)
                        hook_info["recent_success"] = sum(
                            1 for d in deliveries[:10] if isinstance(d, dict) and d.get("status") == "success"
                        )
                        hook_info["recent_failed"] = sum(
                            1 for d in deliveries[:10] if isinstance(d, dict) and d.get("status") == "failed"
                        )
                    else:
                        hook_info["delivery_error"] = f"Unexpected deliveries type: {type(deliveries).__name__}"
            except Exception as e:
                hook_info["delivery_error"] = str(e)
            
            result["webhooks"].append(hook_info)
        
        result["status"] = "success"
        
    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"
    
    return result


def format_webhook_summary(results: List[Dict]) -> str:
    """Format webhook status results for display."""
    output = []
    output.append("=" * 80)
    output.append("PROCORE WEBHOOK STATUS SUMMARY")
    output.append("=" * 80)
    output.append("")
    
    total_projects = len(results)
    projects_with_webhooks = sum(1 for r in results if r.get("webhooks"))
    projects_with_submittals_triggers = sum(
        1 for r in results 
        for w in r.get("webhooks", []) 
        if w.get("has_submittals_update")
    )
    
    output.append(f"Total projects checked: {total_projects}")
    output.append(f"Projects with webhooks: {projects_with_webhooks}")
    output.append(f"Projects with Submittals/update triggers: {projects_with_submittals_triggers}")
    output.append("")
    
    for result in results:
        project_id = result["project_id"]
        project_number = result.get("project_number", "N/A")
        project_name = result.get("project_name", "N/A")
        status = result["status"]
        
        output.append("-" * 80)
        output.append(f"Project ID: {project_id}")
        output.append(f"Project Number: {project_number}")
        output.append(f"Project Name: {project_name}")
        output.append(f"Status: {status}")
        
        if status == "error":
            output.append(f"  Error: {result.get('error', 'Unknown error')}")
        elif status == "no_webhooks":
            output.append("  ⚠️  No webhooks found for this project")
        elif result.get("webhooks"):
            for webhook in result["webhooks"]:
                hook_id = webhook["hook_id"]
                output.append(f"\n  Webhook ID: {hook_id}")
                output.append(f"    Destination URL: {webhook.get('destination_url')}")
                output.append(f"    Namespace: {webhook.get('namespace')}")
                
                if webhook.get("has_submittals_update"):
                    output.append("    ✓ Submittals/update trigger: YES")
                else:
                    output.append("    ✗ Submittals/update trigger: NO")
                
                triggers = webhook.get("triggers", [])
                if triggers:
                    output.append(f"    Triggers ({len(triggers)}):")
                    for trigger in triggers:
                        resource = trigger.get("resource_name", "unknown")
                        event = trigger.get("event_type", "unknown")
                        output.append(f"      - {resource}/{event}")
                
                if "delivery_error" not in webhook:
                    total = webhook.get("total_deliveries", 0)
                    recent_success = webhook.get("recent_success", 0)
                    recent_failed = webhook.get("recent_failed", 0)
                    if total > 0:
                        output.append(f"    Deliveries: {total} total, {recent_success} recent success, {recent_failed} recent failed")
                    else:
                        output.append("    Deliveries: No deliveries yet")
                
                if "delivery_error" in webhook:
                    output.append(f"    ⚠️  Delivery check error: {webhook['delivery_error']}")
        
        output.append("")
    
    output.append("=" * 80)
    return "\n".join(output)


def main():
    """Main function to check webhook status for all projects."""
    app = create_app()
    
    with app.app_context():
        print("Scanning procore_submittals table for unique projects...")
        projects = get_unique_projects(include_name=True)
        
        if not projects:
            print("No projects found in procore_submittals table.")
            return
        
        print(f"Found {len(projects)} unique project(s).")
        print("Checking webhook status...")
        print("-" * 80)
        
        procore_client = get_procore_client()
        namespace = "mile-high-metal-works"
        
        results = []
        for project_id, project_number, project_name in projects:
            result = check_project_webhooks(
                procore_client, project_id, project_number, project_name, namespace
            )
            results.append(result)
        
        # Print formatted summary
        summary = format_webhook_summary(results)
        print(summary)
        
        # Also save JSON output
        output_file = "logs/procore_webhook_status.json"
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            with open(os.path.join(log_dir, "procore_webhook_status.json"), "w") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\nDetailed JSON output saved to: {output_file}")
        except Exception as e:
            print(f"Warning: Could not save JSON output: {e}")


if __name__ == "__main__":
    main()

