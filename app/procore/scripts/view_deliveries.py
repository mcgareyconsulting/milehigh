"""
Script to view recent Procore webhook deliveries/payloads.

Usage:
    python -m app.procore.scripts.view_deliveries [days_back] [limit_per_hook]
    
Examples:
    python -m app.procore.scripts.view_deliveries           # Last 7 days, 20 per hook
    python -m app.procore.scripts.view_deliveries 14        # Last 14 days
    python -m app.procore.scripts.view_deliveries 30 50     # Last 30 days, 50 per hook

Shows what webhooks were sent to your production server,
including delivery status, timestamps, and payloads.
"""

import json
import os
from datetime import datetime
from typing import List, Dict

from app import create_app
from app.procore.client import get_procore_client
from app.procore.webhook_utils import get_unique_projects, get_recent_deliveries
from app.config import Config as cfg


def format_delivery(delivery: Dict) -> str:
    """Format a delivery record for display."""
    lines = []
    created_at = delivery.get("created_at", "unknown")
    status = delivery.get("status", "unknown")
    status_code = delivery.get("status_code")
    
    # Status emoji
    status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⚠️"
    
    lines.append(f"  {status_icon} {status.upper()} (HTTP {status_code}) - {created_at}")
    
    # Show payload if available
    payload = delivery.get("payload")
    if payload:
        if isinstance(payload, dict):
            # Extract key info from payload
            resource_name = payload.get("resource_name")
            event_type = payload.get("event_type")
            resource_id = payload.get("resource_id")
            
            if resource_name or event_type:
                lines.append(f"      Resource: {resource_name}, Event: {event_type}")
            if resource_id:
                lines.append(f"      Resource ID: {resource_id}")
        elif isinstance(payload, str):
            # Truncate if too long
            payload_preview = payload[:200] + "..." if len(payload) > 200 else payload
            lines.append(f"      Payload: {payload_preview}")
    
    # Show error if failed
    error_message = delivery.get("error_message")
    if error_message:
        lines.append(f"      Error: {error_message}")
    
    # Show response body if available
    response_body = delivery.get("response_body")
    if response_body:
        response_preview = str(response_body)[:150] + "..." if len(str(response_body)) > 150 else str(response_body)
        lines.append(f"      Response: {response_preview}")
    
    return "\n".join(lines)


def view_webhook_deliveries(days_back: int = 7, limit_per_hook: int = 20):
    """View recent webhook deliveries for all projects."""
    app = create_app()
    
    with app.app_context():
        print(f"Fetching webhook deliveries from the last {days_back} days...")
        print("=" * 80)
        
        projects = get_unique_projects(include_name=True)
        if not projects:
            print("No projects found in procore_submittals table.")
            return
        
        procore_client = get_procore_client()
        namespace = "mile-high-metal-works"
        
        all_deliveries = []
        total_deliveries = 0
        
        for project_id, project_number, project_name in projects:
            try:
                # Get webhooks for this project
                webhooks = procore_client.list_project_webhooks(project_id, namespace)
                
                if not webhooks:
                    continue
                
                for webhook in webhooks:
                    hook_id = webhook.get("id")
                    if not hook_id:
                        continue
                    
                    # Check if this webhook has Submittals/update trigger
                    try:
                        triggers = procore_client.get_webhook_triggers(project_id, hook_id)
                        has_submittals_update = any(
                            isinstance(t, dict) and 
                            t.get("resource_name") == "Submittals" and 
                            t.get("event_type") == "update"
                            for t in triggers if isinstance(triggers, list) and triggers
                        )
                        
                        if not has_submittals_update:
                            continue  # Skip webhooks without Submittals/update trigger
                    except:
                        continue
                    
                    # Get recent deliveries
                    deliveries = get_recent_deliveries(
                        procore_client, project_id, hook_id, days_back
                    )
                    
                    if deliveries:
                        # Limit deliveries per hook
                        deliveries = deliveries[:limit_per_hook]
                        
                        for delivery in deliveries:
                            delivery["project_id"] = project_id
                            delivery["project_number"] = project_number
                            delivery["project_name"] = project_name
                            delivery["hook_id"] = hook_id
                            all_deliveries.append(delivery)
                            total_deliveries += 1
                        
            except Exception as e:
                print(f"Error processing project {project_id} ({project_number}): {e}")
                continue
        
        # Sort all deliveries by timestamp (most recent first)
        all_deliveries.sort(
            key=lambda x: x.get("created_at", ""), 
            reverse=True
        )
        
        # Display results
        if not all_deliveries:
            print(f"\nNo webhook deliveries found in the last {days_back} days.")
            print("\nNote: This could mean:")
            print("  - No webhooks have been triggered yet")
            print("  - Webhooks are configured but no Submittals have been updated")
            print("  - Check webhook configuration with: python -m app.procore.scripts.check")
            return
        
        print(f"\nFound {total_deliveries} webhook delivery(s) in the last {days_back} days\n")
        print("=" * 80)
        
        # Group by project
        current_project = None
        for delivery in all_deliveries:
            project_id = delivery["project_id"]
            project_number = delivery.get("project_number", "N/A")
            project_name = delivery.get("project_name", "N/A")
            
            # Print project header if changed
            project_key = f"{project_id} - {project_number}"
            if project_key != current_project:
                current_project = project_key
                print(f"\n📁 Project: {project_number} - {project_name} (ID: {project_id})")
                print("-" * 80)
            
            # Print delivery details
            print(format_delivery(delivery))
            print()
        
        # Save to JSON file
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        output_file = os.path.join(log_dir, "procore_webhook_deliveries.json")
        
        try:
            with open(output_file, "w") as f:
                json.dump({
                    "generated_at": datetime.utcnow().isoformat(),
                    "days_back": days_back,
                    "total_deliveries": total_deliveries,
                    "deliveries": all_deliveries
                }, f, indent=2, default=str)
            print("=" * 80)
            print(f"Detailed JSON saved to: {output_file}")
        except Exception as e:
            print(f"Warning: Could not save JSON output: {e}")


def main():
    """Main function."""
    import sys
    
    # Parse command line arguments
    days_back = 7  # Default: last week
    limit_per_hook = 20  # Default: last 20 deliveries per hook
    
    if len(sys.argv) > 1:
        try:
            days_back = int(sys.argv[1])
        except ValueError:
            print(f"Invalid days argument: {sys.argv[1]}. Using default: 7 days")
    
    if len(sys.argv) > 2:
        try:
            limit_per_hook = int(sys.argv[2])
        except ValueError:
            print(f"Invalid limit argument: {sys.argv[2]}. Using default: 20")
    
    view_webhook_deliveries(days_back=days_back, limit_per_hook=limit_per_hook)


if __name__ == "__main__":
    main()

