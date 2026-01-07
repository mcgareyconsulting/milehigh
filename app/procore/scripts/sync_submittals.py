"""
Script to sync submittals from Procore API to the database.

Usage:
    python -m app.procore.scripts.sync_submittals --project-id <project_id>

Fetches submittals from Procore API for a given project_id,
filters for status='Open' and type != 'For Construction',
checks against the database, and adds new submittals to the ProcoreSubmittals table.
"""

import argparse
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.models import db, ProcoreSubmittal
from app.procore.client import get_procore_client
from app.procore.procore import get_project_info, get_submittal_by_id
from app.procore.helpers import parse_ball_in_court_from_submittal
from app.logging_config import get_logger

logger = get_logger(__name__)


def extract_field_value(data, field_name, default=None):
    """Extract a field value from submittal data, handling both dict and string formats."""
    field_obj = data.get(field_name, default)
    if isinstance(field_obj, dict):
        return field_obj.get("name") or field_obj.get("value") or default
    elif isinstance(field_obj, str):
        return field_obj
    return default


def create_submittal_from_api_data(project_id, submittal_data):
    """
    Create a new ProcoreSubmittal record from API submittal data.
    
    Args:
        project_id: Procore project ID
        submittal_data: Dict containing submittal data from Procore API
        
    Returns:
        tuple: (created: bool, record: ProcoreSubmittal or None, error_message: str or None)
    """
    try:
        submittal_id = submittal_data.get("id")
        if not submittal_id:
            error_msg = "Submittal data missing 'id' field"
            logger.error(error_msg)
            return False, None, error_msg
        
        submittal_id_str = str(submittal_id)
        
        # Check if submittal already exists
        existing = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id_str).first()
        if existing:
            logger.info(f"Submittal {submittal_id_str} already exists in database, skipping")
            return False, existing, None
        
        # Get project information
        project_info = get_project_info(project_id)
        if not project_info:
            error_msg = f"Failed to fetch project info for project {project_id}"
            logger.error(error_msg)
            return False, None, error_msg
        
        # Parse ball_in_court from submittal data
        parsed = parse_ball_in_court_from_submittal(submittal_data)
        ball_in_court = parsed.get("ball_in_court") if parsed else None
        
        # Extract fields
        status = extract_field_value(submittal_data, "status")
        status = str(status).strip() if status else None
        
        submittal_type = extract_field_value(submittal_data, "type")
        submittal_type = str(submittal_type).strip() if submittal_type else None
        
        title = submittal_data.get("title")
        title = str(title).strip() if title else None
        
        # Extract submittal_manager
        submittal_manager_obj = submittal_data.get("submittal_manager") or submittal_data.get("manager")
        if isinstance(submittal_manager_obj, dict):
            submittal_manager = submittal_manager_obj.get("name") or submittal_manager_obj.get("login")
        elif isinstance(submittal_manager_obj, str):
            submittal_manager = submittal_manager_obj
        else:
            submittal_manager = None
        submittal_manager = str(submittal_manager).strip() if submittal_manager else None
        
        # Extract order_number if available
        order_number = submittal_data.get("order_number")
        if order_number is not None:
            try:
                order_number = float(order_number)
            except (ValueError, TypeError):
                order_number = None
        
        # Extract notes if available
        notes = submittal_data.get("notes")
        notes = str(notes).strip() if notes else None
        
        # Double-check it doesn't exist (race condition protection)
        existing_check = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id_str).first()
        if existing_check:
            logger.info(
                f"Submittal {submittal_id_str} was created by another process. "
                f"Returning existing record."
            )
            return False, existing_check, None
        
        # Create new ProcoreSubmittal record
        new_submittal = ProcoreSubmittal(
            submittal_id=submittal_id_str,
            procore_project_id=str(project_id),
            project_number=str(project_info.get("project_number", "")).strip() or None,
            project_name=project_info.get("name"),
            title=title,
            status=status,
            type=submittal_type,
            ball_in_court=str(ball_in_court).strip() if ball_in_court else None,
            submittal_manager=submittal_manager,
            order_number=order_number,
            notes=notes,
            submittal_drafting_status='',  # Default empty string
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        
        db.session.add(new_submittal)
        
        try:
            db.session.commit()
            logger.info(
                f"Created submittal record: submittal_id={submittal_id_str}, "
                f"project_id={project_id}, title={title}"
            )
            return True, new_submittal, None
        except IntegrityError as integrity_error:
            # Handle unique constraint violations
            logger.warning(
                f"Unique constraint violation during commit for submittal {submittal_id_str}. "
                f"Rolling back and fetching existing record."
            )
            db.session.rollback()
            existing_after_error = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id_str).first()
            if existing_after_error:
                logger.info(f"Found existing record, returning it")
                return False, existing_after_error, None
            else:
                error_msg = f"Unique constraint violation but no existing record found: {integrity_error}"
                logger.error(error_msg)
                return False, None, error_msg
        except Exception as commit_error:
            logger.error(f"Unexpected error during commit: {commit_error}", exc_info=True)
            db.session.rollback()
            raise
        
    except Exception as e:
        error_type = type(e).__name__
        error_msg = f"Error creating submittal from API data: {error_type} - {str(e)}"
        logger.error(error_msg, exc_info=True)
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(f"Error during rollback: {rollback_error}", exc_info=True)
        return False, None, error_msg


def sync_submittals_for_project(project_id):
    """
    Sync submittals from Procore API to database for a given project.
    
    Args:
        project_id: Procore project ID
        
    Returns:
        dict: Summary of sync operation
    """
    logger.info(f"Starting submittal sync for project_id: {project_id}")
    
    procore_client = get_procore_client()
    
    # Get all submittals for the project (with pagination)
    logger.info(f"Fetching submittals from Procore API for project {project_id}...")
    try:
        all_submittals = procore_client.get_submittals(project_id)
        
        # The API method now handles pagination and returns a list
        if not isinstance(all_submittals, list):
            logger.error(f"Unexpected response type from get_submittals: {type(all_submittals)}, value: {all_submittals}")
            return {
                "status": "error",
                "message": f"Failed to fetch submittals: unexpected response type {type(all_submittals).__name__}",
                "project_id": project_id,
                "total_fetched": 0,
                "filtered": 0,
                "created": 0,
                "skipped": 0,
                "errors": 0
            }
    except Exception as e:
        logger.error(f"Error fetching submittals: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to fetch submittals: {str(e)}",
            "project_id": project_id,
            "total_fetched": 0,
            "filtered": 0,
            "created": 0,
            "skipped": 0,
            "errors": 0
        }
    
    logger.info(f"Fetched {len(all_submittals)} submittals from API")
    
    # Filter submittals: status='Open' and type != 'For Construction'
    filtered_submittals = []
    for submittal in all_submittals:
        if not isinstance(submittal, dict):
            continue
        
        # Extract status
        status = extract_field_value(submittal, "status")
        status = str(status).strip() if status else None
        
        # Extract type
        submittal_type = extract_field_value(submittal, "type")
        submittal_type = str(submittal_type).strip() if submittal_type else None
        
        # Filter: status must be 'Open' and type must NOT be 'For Construction'
        if status == "Open" and submittal_type != "For Construction":
            filtered_submittals.append(submittal)
    
    logger.info(f"Filtered to {len(filtered_submittals)} submittals (status='Open' and type != 'For Construction')")
    
    # Process each filtered submittal
    created_count = 0
    skipped_count = 0
    error_count = 0
    errors = []
    
    for submittal in filtered_submittals:
        submittal_id = submittal.get("id")
        if not submittal_id:
            logger.warning(f"Skipping submittal without ID: {submittal}")
            error_count += 1
            errors.append(f"Submittal missing ID: {submittal.get('title', 'Unknown')}")
            continue
        
        # Check if we need to fetch full submittal details for ball_in_court
        # The list response might not include approvers/workflow data
        submittal_data = submittal
        if "approvers" not in submittal and "ball_in_court" not in submittal:
            # Try to fetch full details for more complete data
            try:
                full_submittal = get_submittal_by_id(project_id, submittal_id)
                if isinstance(full_submittal, dict):
                    # Merge full details with list data (full details take precedence)
                    submittal_data = {**submittal, **full_submittal}
                    logger.debug(f"Fetched full details for submittal {submittal_id}")
            except Exception as e:
                # If fetching full details fails, continue with list data
                logger.warning(f"Could not fetch full details for submittal {submittal_id}: {e}. Using list data.")
        
        created, record, error_msg = create_submittal_from_api_data(project_id, submittal_data)
        
        if created:
            created_count += 1
            logger.info(f"✓ Created submittal {submittal_id}: {submittal.get('title', 'N/A')}")
        elif record:
            skipped_count += 1
            logger.debug(f"⊘ Skipped submittal {submittal_id} (already exists)")
        else:
            error_count += 1
            error_detail = f"Submittal {submittal_id}: {error_msg or 'Unknown error'}"
            errors.append(error_detail)
            logger.error(f"✗ Failed to create submittal {submittal_id}: {error_msg}")
    
    summary = {
        "status": "success" if error_count == 0 else "partial" if created_count > 0 else "error",
        "message": f"Sync completed: {created_count} created, {skipped_count} skipped, {error_count} errors",
        "project_id": project_id,
        "total_fetched": len(all_submittals),
        "filtered": len(filtered_submittals),
        "created": created_count,
        "skipped": skipped_count,
        "errors": error_count,
        "error_details": errors if errors else None
    }
    
    logger.info(f"Sync summary: {summary['message']}")
    return summary


def main():
    """Main function to sync submittals for a project."""
    parser = argparse.ArgumentParser(
        description="Sync submittals from Procore API to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync submittals for a specific project
  python -m app.procore.scripts.sync_submittals --project-id 12345
        """
    )
    
    parser.add_argument(
        "--project-id",
        type=int,
        required=True,
        help="Procore project ID to sync submittals for"
    )
    
    args = parser.parse_args()
    
    app = create_app()
    
    with app.app_context():
        print(f"Syncing submittals for Project ID: {args.project_id}")
        print("-" * 60)
        
        summary = sync_submittals_for_project(args.project_id)
        
        print("\n" + "=" * 60)
        print("SYNC SUMMARY")
        print("=" * 60)
        print(f"Status: {summary['status']}")
        print(f"Message: {summary['message']}")
        print(f"Total fetched from API: {summary['total_fetched']}")
        print(f"Filtered (Open, not 'For Construction'): {summary['filtered']}")
        print(f"Created: {summary['created']}")
        print(f"Skipped (already exists): {summary['skipped']}")
        print(f"Errors: {summary['errors']}")
        
        if summary.get('error_details'):
            print("\nErrors:")
            for error in summary['error_details']:
                print(f"  - {error}")


if __name__ == "__main__":
    main()

