"""
Script to delete all Procore webhooks for projects in procore_submittals.

Usage:
    # Delete webhooks for all projects in database
    python -m app.procore.scripts.delete
    
    # Delete webhooks for a single project
    python -m app.procore.scripts.delete --project-id <project_id>

Deletes all webhooks found for each project to clean up and start fresh.
"""

import argparse
from typing import Dict, Optional

from app import create_app
from app.models import db, ProcoreSubmittal
from app.procore.client import get_procore_client
from app.procore.webhook_utils import get_unique_projects, log_operation


def delete_all_webhooks_for_project(procore_client, project_id: int, project_number: Optional[str],
                                    namespace: str = "mile-high-metal-works") -> dict:
    """Delete all webhooks for a specific project."""
    log_file = "procore_webhook_deletions.log"
    
    result = {
        "project_id": project_id,
        "project_number": project_number,
        "deleted_count": 0,
        "errors": []
    }
    
    try:
        # List all webhooks for this project
        webhooks = procore_client.list_project_webhooks(project_id, namespace)
        
        if not webhooks:
            log_operation(
                log_file,
                "delete_webhooks",
                project_id,
                project_number,
                {"message": "No webhooks found"},
                "skipped"
            )
            result["status"] = "no_webhooks"
            return result
        
        # Delete each webhook
        for webhook in webhooks:
            if not isinstance(webhook, dict):
                continue
            
            hook_id = webhook.get("id")
            if not hook_id:
                continue
            
            try:
                delete_response = procore_client.delete_webhook(project_id, hook_id)
                log_operation(
                    log_file,
                    "delete_webhook",
                    project_id,
                    project_number,
                    {"hook_id": hook_id, "response": delete_response or {}},
                    "success"
                )
                result["deleted_count"] += 1
            except Exception as e:
                error_msg = str(e)
                log_operation(
                    log_file,
                    "delete_webhook",
                    project_id,
                    project_number,
                    {"hook_id": hook_id, "error": error_msg},
                    "error"
                )
                result["errors"].append({
                    "hook_id": hook_id,
                    "error": error_msg
                })
        
        result["status"] = "success"
        
    except Exception as e:
        error_msg = str(e)
        log_operation(
            log_file,
            "delete_webhooks",
            project_id,
            project_number,
            {"error": error_msg},
            "error"
        )
        result["status"] = "error"
        result["error"] = error_msg
    
    return result


def get_project_number(project_id: int) -> Optional[str]:
    """Get project number for a given project ID from the database."""
    result = db.session.query(ProcoreSubmittal.project_number).filter(
        ProcoreSubmittal.procore_project_id == project_id
    ).first()
    
    return result[0] if result else None


def main():
    """Main function to delete all webhooks for projects."""
    parser = argparse.ArgumentParser(
        description="Delete Procore webhooks for projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete webhooks for all projects in database
  python -m app.procore.scripts.delete
  
  # Delete webhooks for a specific project by ID
  python -m app.procore.scripts.delete --project-id 12345
        """
    )
    
    parser.add_argument(
        "--project-id",
        type=int,
        help="Procore project ID to delete webhooks for (single project mode)"
    )
    
    args = parser.parse_args()
    
    app = create_app()
    
    with app.app_context():
        # Single project mode
        if args.project_id:
            project_id = args.project_id
            project_number = get_project_number(project_id)
            
            print(f"Deleting webhooks for Project ID: {project_id}")
            if project_number:
                print(f"Project Number: {project_number}")
            else:
                print("(Project not found in database - will proceed anyway)")
            
            print("WARNING: This will delete ALL webhooks for this project!")
            
            # Ask for confirmation
            response = input("\nAre you sure you want to delete all webhooks? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled.")
                return
            
            print("-" * 60)
            
            procore_client = get_procore_client()
            namespace = "mile-high-metal-works"
            
            result = delete_all_webhooks_for_project(procore_client, project_id, project_number, namespace)
            
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print(f"Project ID: {project_id}")
            if project_number:
                print(f"Project Number: {project_number}")
            print(f"Webhooks deleted: {result['deleted_count']}")
            if result["status"] == "no_webhooks":
                print("Status: No webhooks found")
            elif result["status"] == "error":
                print(f"Status: Error - {result.get('error', 'Unknown error')}")
            else:
                print("Status: Success")
            if result.get("errors"):
                print(f"Errors encountered: {len(result['errors'])}")
            print(f"\nDetailed responses logged to: logs/procore_webhook_deletions.log")
            return
        
        # Batch mode: delete webhooks for all projects in database
        print("Scanning procore_submittals table for unique projects...")
        projects = get_unique_projects()
        
        if not projects:
            print("No projects found in procore_submittals table.")
            return
        
        print(f"Found {len(projects)} unique project(s).")
        print("WARNING: This will delete ALL webhooks for these projects!")
        
        # Ask for confirmation
        response = input("\nAre you sure you want to delete all webhooks? (yes/no): ")
        if response.lower() != "yes":
            print("Cancelled.")
            return
        
        print("-" * 60)
        
        procore_client = get_procore_client()
        namespace = "mile-high-metal-works"
        
        results = {
            "total": len(projects),
            "deleted": 0,
            "errors": 0,
            "no_webhooks": 0,
            "details": []
        }
        
        for project_id, project_number in projects:
            print(f"\nProcessing Project ID: {project_id} (Project Number: {project_number})")
            result = delete_all_webhooks_for_project(procore_client, project_id, project_number, namespace)
            results["details"].append(result)
            
            if result["status"] == "success":
                results["deleted"] += result["deleted_count"]
            elif result["status"] == "no_webhooks":
                results["no_webhooks"] += 1
            else:
                results["errors"] += 1
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total projects processed: {results['total']}")
        print(f"Webhooks deleted: {results['deleted']}")
        print(f"Projects with no webhooks: {results['no_webhooks']}")
        print(f"Projects with errors: {results['errors']}")
        print(f"\nDetailed responses logged to: logs/procore_webhook_deletions.log")


if __name__ == "__main__":
    main()

