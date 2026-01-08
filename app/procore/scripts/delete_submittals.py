"""
Script to delete all submittals from the database for a specific project.

Usage:
    python -m app.procore.scripts.delete_submittals --project-id <project_id> [--force]

Deletes all submittals from the ProcoreSubmittals table for the given project_id.
Useful for bulk resetting submittals when there's an error.

Safety:
    - By default, requires confirmation before deleting
    - Use --force flag to skip confirmation
    - Shows summary of what will be deleted before confirmation
"""

import argparse

from app import create_app
from app.models import db, ProcoreSubmittal
from app.procore.procore import get_project_info
from app.logging_config import get_logger

logger = get_logger(__name__)


def delete_submittals_for_project(project_id, force=False):
    """
    Delete all submittals from the database for a given project.
    
    Args:
        project_id: Procore project ID
        force: If True, skip confirmation prompt
        
    Returns:
        dict: Summary of deletion operation
    """
    logger.info(f"Starting submittal deletion for project_id: {project_id}")
    
    # Get project info for display
    project_info = get_project_info(project_id)
    project_name = project_info.get("name") if project_info else "Unknown"
    project_number = project_info.get("project_number") if project_info else "Unknown"
    
    # Find all submittals for this project
    submittals = ProcoreSubmittal.query.filter_by(
        procore_project_id=str(project_id)
    ).all()
    
    count = len(submittals)
    
    if count == 0:
        logger.info(f"No submittals found for project {project_id}")
        return {
            "status": "success",
            "message": f"No submittals found for project {project_id}",
            "project_id": project_id,
            "project_name": project_name,
            "project_number": project_number,
            "deleted": 0
        }
    
    # Display summary
    print(f"\n{'=' * 60}")
    print("DELETION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Project ID: {project_id}")
    print(f"Project Name: {project_name}")
    print(f"Project Number: {project_number}")
    print(f"Submittals to delete: {count}")
    print(f"{'=' * 60}\n")
    
    # Show sample submittals (first 5)
    if count > 0:
        print("Sample submittals to be deleted (first 5):")
        for i, submittal in enumerate(submittals[:5], 1):
            print(f"  {i}. ID: {submittal.submittal_id}, Title: {submittal.title or 'N/A'}")
        if count > 5:
            print(f"  ... and {count - 5} more")
        print()
    
    # Confirmation prompt (unless --force)
    if not force:
        response = input("Are you sure you want to delete all these submittals? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            logger.info(f"Deletion cancelled by user for project {project_id}")
            return {
                "status": "cancelled",
                "message": "Deletion cancelled by user",
                "project_id": project_id,
                "project_name": project_name,
                "project_number": project_number,
                "deleted": 0
            }
    
    # Perform deletion
    try:
        deleted_count = 0
        error_count = 0
        errors = []
        
        for submittal in submittals:
            try:
                submittal_id = submittal.submittal_id
                title = submittal.title or "N/A"
                
                db.session.delete(submittal)
                deleted_count += 1
                logger.debug(f"Marked submittal {submittal_id} ({title}) for deletion")
            except Exception as e:
                error_count += 1
                error_msg = f"Error deleting submittal {submittal.submittal_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)
        
        # Commit all deletions
        if deleted_count > 0:
            db.session.commit()
            logger.info(f"Successfully deleted {deleted_count} submittals for project {project_id}")
        
        summary = {
            "status": "success" if error_count == 0 else "partial",
            "message": f"Deleted {deleted_count} submittals" + (f", {error_count} errors" if error_count > 0 else ""),
            "project_id": project_id,
            "project_name": project_name,
            "project_number": project_number,
            "deleted": deleted_count,
            "errors": error_count,
            "error_details": errors if errors else None
        }
        
        return summary
        
    except Exception as e:
        # Rollback on error
        db.session.rollback()
        error_msg = f"Error during deletion: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "error",
            "message": error_msg,
            "project_id": project_id,
            "project_name": project_name,
            "project_number": project_number,
            "deleted": 0,
            "errors": count,
            "error_details": [error_msg]
        }


def main():
    """Main function to delete submittals for a project."""
    parser = argparse.ArgumentParser(
        description="Delete all submittals from database for a project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete submittals with confirmation prompt
  python -m app.procore.scripts.delete_submittals --project-id 12345
  
  # Delete submittals without confirmation (use with caution)
  python -m app.procore.scripts.delete_submittals --project-id 12345 --force
        """
    )
    
    parser.add_argument(
        "--project-id",
        type=int,
        required=True,
        help="Procore project ID to delete submittals for"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt and delete immediately"
    )
    
    args = parser.parse_args()
    
    app = create_app()
    
    with app.app_context():
        print(f"Deleting submittals for Project ID: {args.project_id}")
        if args.force:
            print("⚠️  FORCE MODE: Skipping confirmation prompt")
        print("-" * 60)
        
        summary = delete_submittals_for_project(args.project_id, force=args.force)
        
        print("\n" + "=" * 60)
        print("DELETION RESULT")
        print("=" * 60)
        print(f"Status: {summary['status']}")
        print(f"Message: {summary['message']}")
        print(f"Project ID: {summary['project_id']}")
        print(f"Project Name: {summary.get('project_name', 'N/A')}")
        print(f"Project Number: {summary.get('project_number', 'N/A')}")
        print(f"Deleted: {summary['deleted']}")
        
        if summary.get('errors', 0) > 0:
            print(f"Errors: {summary['errors']}")
            if summary.get('error_details'):
                print("\nError Details:")
                for error in summary['error_details']:
                    print(f"  - {error}")


if __name__ == "__main__":
    main()

