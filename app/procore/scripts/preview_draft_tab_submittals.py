"""
Script to preview and load missing submittals for the 'Draft' tab in Drafting Work Load.

The 'Draft' tab should contain:
- All submittals with status != 'Open'
- Type: DRR (Drafting Release Review) OR Sub GC (Submittal for GC Approval) - various spellings
- Exclude: "For Construction" type

This script scans all projects and compares against the database to show how many
submittals are missing that should be in the 'Draft' tab.

Usage:
    # Preview only (default):
    python -m app.procore.scripts.preview_draft_tab_submittals
    
    # Load missing submittals into database:
    python -m app.procore.scripts.preview_draft_tab_submittals --load
"""

import json
import os
import sys
import argparse
from typing import List, Dict, Optional, Set
from collections import defaultdict
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.procore.client import get_procore_client
from app.models import db, ProcoreSubmittal
from app.config import Config as cfg
from app.procore.helpers import parse_ball_in_court_from_submittal
from app.procore.procore import get_submittal_by_id, get_project_info


def extract_status(submittal_data: Dict) -> Optional[str]:
    """Extract status from submittal data, handling both dict and string formats."""
    status_obj = submittal_data.get("status")
    if isinstance(status_obj, dict):
        return status_obj.get("name")
    elif isinstance(status_obj, str):
        return status_obj
    return None


def extract_type(submittal_data: Dict) -> Optional[str]:
    """Extract type from submittal data, handling both dict and string formats."""
    type_obj = submittal_data.get("type")
    if isinstance(type_obj, dict):
        return type_obj.get("name")
    elif isinstance(type_obj, str):
        return type_obj
    return None


def extract_submittal_manager(submittal_data: Dict) -> Optional[str]:
    """Extract submittal_manager from submittal data, handling both dict and string formats."""
    manager_obj = submittal_data.get("submittal_manager") or submittal_data.get("manager")
    if isinstance(manager_obj, dict):
        return manager_obj.get("name") or manager_obj.get("login")
    elif isinstance(manager_obj, str):
        return manager_obj
    return None


def normalize_name(name: Optional[str]) -> Optional[str]:
    """Normalize a name for comparison (strip whitespace)."""
    if not name:
        return None
    return str(name).strip()


def is_valid_draft_tab_type(submittal_type: Optional[str]) -> bool:
    """Check if submittal type is valid for Draft tab (DRR or Sub GC, but not For Construction)."""
    if not submittal_type:
        return False
    
    type_normalized = normalize_name(submittal_type)
    
    # Exclude "For Construction"
    if type_normalized and "for construction" in type_normalized.lower():
        return False
    
    # Valid types for Draft tab:
    valid_types = [
        "Drafting Release Review",
        "Submittal for GC  Approval",
        "Submittal for GC Approval",
        "Submittal for Gc  Approval",
        "Submittal for Gc Approval",
        "Submittal For Gc  Approval",
        "Submittal For Gc Approval",
    ]
    
    # Case-insensitive comparison
    type_lower = type_normalized.lower()
    for valid_type in valid_types:
        if type_lower == valid_type.lower():
            return True
    
    return False


def is_non_open_status(status: Optional[str]) -> bool:
    """Check if status is NOT 'Open' (case-insensitive)."""
    if not status:
        return True  # Treat None/empty as non-Open
    
    status_normalized = normalize_name(status)
    return status_normalized.lower() != "open"


def get_all_projects(procore_client) -> List[Dict]:
    """Get all projects from Procore API."""
    print(f"Fetching all projects for company {cfg.PROD_PROCORE_COMPANY_ID}...")
    try:
        projects = procore_client.get_projects(cfg.PROD_PROCORE_COMPANY_ID)
        if not isinstance(projects, list):
            print(f"Warning: Expected list but got {type(projects).__name__}")
            return []
        print(f"Found {len(projects)} project(s).")
        return projects
    except Exception as e:
        print(f"Error fetching projects: {e}")
        return []


def get_submittals_for_project(procore_client, project_id: int, project_name: str) -> List[Dict]:
    """Get all submittals for a project."""
    try:
        submittals = procore_client.get_submittals(project_id)
        
        # Handle wrapped responses
        if isinstance(submittals, dict) and 'data' in submittals:
            submittals = submittals['data']
        
        if not isinstance(submittals, list):
            return []
        
        return submittals
    except Exception as e:
        print(f"  Warning: Error fetching submittals for project {project_id} ({project_name}): {e}")
        return []


def filter_draft_tab_submittals(submittals: List[Dict]) -> List[Dict]:
    """Filter submittals that should be in the Draft tab."""
    filtered = []
    for submittal in submittals:
        status = extract_status(submittal)
        submittal_type = extract_type(submittal)
        
        # Must be non-Open status
        if not is_non_open_status(status):
            continue
        
        # Must be valid type (DRR or Sub GC, not For Construction)
        if not is_valid_draft_tab_type(submittal_type):
            continue
        
        filtered.append(submittal)
    
    return filtered


def get_db_submittal_ids() -> Set[str]:
    """Get set of all submittal IDs from database."""
    submittals = ProcoreSubmittal.query.all()
    return {str(s.submittal_id) for s in submittals}


def preview_draft_tab_submittals(procore_client) -> Dict:
    """Preview submittals that should be in the Draft tab."""
    print(f"\n{'='*80}")
    print("Preview: Missing Submittals for 'Draft' Tab")
    print("="*80)
    print("\nCriteria:")
    print("  - Status: NOT 'Open' (all other statuses)")
    print("  - Type: DRR (Drafting Release Review) OR Sub GC (Submittal for GC Approval)")
    print("  - Exclude: 'For Construction' type")
    print(f"{'='*80}\n")
    
    # Get all projects
    projects = get_all_projects(procore_client)
    if not projects:
        print("No projects found. Exiting.")
        return {}
    
    # Get database submittal IDs for comparison
    print("\nLoading submittal IDs from database...")
    db_submittal_ids = get_db_submittal_ids()
    print(f"Found {len(db_submittal_ids)} submittal(s) in database.\n")
    
    # Track results
    results = {
        "total_projects": len(projects),
        "projects_scanned": 0,
        "projects_with_matches": 0,
        "total_api_submittals": 0,
        "total_db_submittals": len(db_submittal_ids),
        "api_submittals_in_db": 0,
        "api_submittals_missing_from_db": 0,
        "by_status": defaultdict(lambda: {
            "total": 0,
            "in_db": 0,
            "missing_from_db": 0
        }),
        "by_type": defaultdict(lambda: {
            "total": 0,
            "in_db": 0,
            "missing_from_db": 0
        }),
        "project_details": [],
        "missing_submittals": []
    }
    
    # Scan each project
    print("Scanning projects for Draft tab submittals...")
    print("-" * 80)
    
    for i, project in enumerate(projects, 1):
        project_id = project.get("id")
        project_name = project.get("name", "Unknown")
        project_number = project.get("project_number", "Unknown")
        
        if not project_id:
            continue
        
        results["projects_scanned"] += 1
        
        # Get submittals for this project
        submittals = get_submittals_for_project(procore_client, project_id, project_name)
        
        # Filter for Draft tab criteria
        draft_tab_submittals = filter_draft_tab_submittals(submittals)
        
        if draft_tab_submittals:
            results["projects_with_matches"] += 1
            results["total_api_submittals"] += len(draft_tab_submittals)
            
            project_detail = {
                "project_id": project_id,
                "project_name": project_name,
                "project_number": project_number,
                "submittals": []
            }
            
            for submittal in draft_tab_submittals:
                submittal_id = str(submittal.get("id", ""))
                title = submittal.get("title", "No title")
                status = extract_status(submittal)
                submittal_type = extract_type(submittal)
                
                # Normalize for grouping
                status_key = normalize_name(status) or "Unknown Status"
                type_key = normalize_name(submittal_type) or "Unknown Type"
                
                in_db = submittal_id in db_submittal_ids
                
                # Update statistics
                results["by_status"][status_key]["total"] += 1
                results["by_type"][type_key]["total"] += 1
                
                if in_db:
                    results["api_submittals_in_db"] += 1
                    results["by_status"][status_key]["in_db"] += 1
                    results["by_type"][type_key]["in_db"] += 1
                else:
                    results["api_submittals_missing_from_db"] += 1
                    results["by_status"][status_key]["missing_from_db"] += 1
                    results["by_type"][type_key]["missing_from_db"] += 1
                    
                    results["missing_submittals"].append({
                        "submittal_id": submittal_id,
                        "project_id": project_id,
                        "project_name": project_name,
                        "project_number": project_number,
                        "title": title,
                        "status": status,
                        "type": submittal_type
                    })
                
                project_detail["submittals"].append({
                    "submittal_id": submittal_id,
                    "title": title,
                    "status": status,
                    "type": submittal_type,
                    "in_database": in_db
                })
            
            results["project_details"].append(project_detail)
            
            print(f"[{i}/{len(projects)}] {project_name} ({project_number}): "
                  f"Found {len(draft_tab_submittals)} Draft tab submittal(s)")
        
        # Progress indicator
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(projects)} projects scanned...")
    
    return results


def print_summary(results: Dict):
    """Print a formatted summary of the preview."""
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total Projects Scanned: {results['total_projects']}")
    print(f"Projects with Draft Tab Submittals: {results['projects_with_matches']}")
    print(f"\nTotal Draft Tab Submittals in Procore API: {results['total_api_submittals']}")
    print(f"  - Found in Database: {results['api_submittals_in_db']}")
    print(f"  - Missing from Database: {results['api_submittals_missing_from_db']}")
    print(f"\nTotal Submittals in Database: {results['total_db_submittals']}")
    
    # Print breakdown by status
    if results['by_status']:
        print(f"\n{'='*80}")
        print("BREAKDOWN BY STATUS")
        print(f"{'='*80}")
        
        sorted_statuses = sorted(
            results['by_status'].items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )
        
        for status_name, status_data in sorted_statuses:
            print(f"\n{status_name}:")
            print(f"  Total: {status_data['total']}")
            print(f"  In Database: {status_data['in_db']}")
            print(f"  Missing from Database: {status_data['missing_from_db']}")
    
    # Print breakdown by type
    if results['by_type']:
        print(f"\n{'='*80}")
        print("BREAKDOWN BY TYPE")
        print(f"{'='*80}")
        
        sorted_types = sorted(
            results['by_type'].items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )
        
        for type_name, type_data in sorted_types:
            print(f"\n{type_name}:")
            print(f"  Total: {type_data['total']}")
            print(f"  In Database: {type_data['in_db']}")
            print(f"  Missing from Database: {type_data['missing_from_db']}")
    
    if results['missing_submittals']:
        print(f"\n{'='*80}")
        print(f"MISSING SUBMITTALS ({len(results['missing_submittals'])} total)")
        print(f"{'='*80}")
        
        # Group missing submittals by status
        missing_by_status = defaultdict(list)
        for submittal in results['missing_submittals']:
            status_name = normalize_name(submittal.get('status')) or "Unknown Status"
            missing_by_status[status_name].append(submittal)
        
        for status_name in sorted(missing_by_status.keys()):
            submittals = missing_by_status[status_name]
            print(f"\n--- {status_name} ({len(submittals)} missing) ---")
            for i, submittal in enumerate(submittals[:20], 1):  # Show first 20 per status
                print(f"\n  [{i}] Submittal ID: {submittal['submittal_id']}")
                print(f"      Project: {submittal['project_name']} ({submittal['project_number']})")
                print(f"      Title: {submittal['title']}")
                print(f"      Type: {submittal.get('type', 'N/A')}")
            if len(submittals) > 20:
                print(f"\n  ... and {len(submittals) - 20} more")
    else:
        print("\n✓ All Draft tab submittals are present in the database!")


def create_submittal_from_api_data(procore_client, project_id: int, submittal_id: str, submittal_data: Dict) -> tuple:
    """
    Create a new ProcoreSubmittal record in the database from API data.
    
    Args:
        procore_client: Procore API client
        project_id: Procore project ID
        submittal_id: Procore submittal ID
        submittal_data: Submittal data from API
        
    Returns:
        tuple: (created: bool, record: ProcoreSubmittal or None, error_message: str or None)
    """
    try:
        # Check if submittal already exists
        existing = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
        if existing:
            return False, existing, None
        
        # Get project information
        project_info = get_project_info(project_id)
        if not project_info:
            return False, None, f"Failed to fetch project info for project {project_id}"
        
        # Parse ball_in_court from submittal data
        parsed = parse_ball_in_court_from_submittal(submittal_data)
        ball_in_court = parsed.get("ball_in_court") if parsed else None
        
        # Extract status
        status = extract_status(submittal_data)
        status = str(status).strip() if status else None
        
        # Extract type
        submittal_type = extract_type(submittal_data)
        submittal_type = str(submittal_type).strip() if submittal_type else None
        
        # Extract title
        title = submittal_data.get("title")
        title = str(title).strip() if title else None
        
        # Extract submittal_manager
        submittal_manager = extract_submittal_manager(submittal_data)
        submittal_manager = str(submittal_manager).strip() if submittal_manager else None
        
        # Double-check it doesn't exist (race condition protection)
        existing_check = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
        if existing_check:
            return False, existing_check, None
        
        # Create new ProcoreSubmittal record
        new_submittal = ProcoreSubmittal(
            submittal_id=str(submittal_id),
            procore_project_id=str(project_id),
            project_number=str(project_info.get("project_number", "")).strip() or None,
            project_name=project_info.get("name"),
            title=title,
            status=status,
            type=submittal_type,
            ball_in_court=str(ball_in_court).strip() if ball_in_court else None,
            submittal_manager=submittal_manager,
            # submittal_drafting_status uses model default of '' (empty string)
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        
        db.session.add(new_submittal)
        
        try:
            db.session.commit()
            return True, new_submittal, None
        except IntegrityError:
            # Handle unique constraint violations
            db.session.rollback()
            existing_after_error = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
            if existing_after_error:
                return False, existing_after_error, None
            else:
                return False, None, "Unique constraint violation but no existing record found"
        except Exception as commit_error:
            db.session.rollback()
            return False, None, f"Error during commit: {str(commit_error)}"
            
    except Exception as e:
        db.session.rollback()
        return False, None, f"Error creating submittal: {str(e)}"


def load_missing_submittals(procore_client, missing_submittals: List[Dict]) -> Dict:
    """Load missing submittals into the database."""
    print(f"\n{'='*80}")
    print(f"Loading {len(missing_submittals)} missing submittals into database...")
    print(f"{'='*80}\n")
    
    results = {
        "total": len(missing_submittals),
        "created": 0,
        "already_exists": 0,
        "errors": 0,
        "error_details": []
    }
    
    for i, submittal_info in enumerate(missing_submittals, 1):
        submittal_id = submittal_info['submittal_id']
        project_id = submittal_info['project_id']
        project_name = submittal_info['project_name']
        title = submittal_info.get('title', 'No title')
        
        print(f"[{i}/{len(missing_submittals)}] Loading submittal {submittal_id} from {project_name}...", end=" ")
        
        try:
            # Fetch full submittal data from API
            submittal_data = get_submittal_by_id(project_id, int(submittal_id))
            
            if not isinstance(submittal_data, dict):
                error_msg = f"Failed to fetch submittal data - got {type(submittal_data).__name__}"
                print(f"ERROR: {error_msg}")
                results["errors"] += 1
                results["error_details"].append({
                    "submittal_id": submittal_id,
                    "project_id": project_id,
                    "error": error_msg
                })
                continue
            
            # Create submittal record
            created, record, error_msg = create_submittal_from_api_data(
                procore_client, project_id, submittal_id, submittal_data
            )
            
            if created:
                print("✓ Created")
                results["created"] += 1
            elif record:
                print("⚠ Already exists")
                results["already_exists"] += 1
            else:
                print(f"ERROR: {error_msg}")
                results["errors"] += 1
                results["error_details"].append({
                    "submittal_id": submittal_id,
                    "project_id": project_id,
                    "error": error_msg
                })
        
        except Exception as e:
            print(f"ERROR: {str(e)}")
            results["errors"] += 1
            results["error_details"].append({
                "submittal_id": submittal_id,
                "project_id": project_id,
                "error": str(e)
            })
        
        # Progress indicator every 10 items
        if i % 10 == 0:
            print(f"\n  Progress: {i}/{len(missing_submittals)} processed "
                  f"({results['created']} created, {results['already_exists']} existed, {results['errors']} errors)")
    
    return results


def print_load_summary(load_results: Dict):
    """Print a summary of the load operation."""
    print(f"\n{'='*80}")
    print("LOAD SUMMARY")
    print(f"{'='*80}")
    print(f"Total Processed: {load_results['total']}")
    print(f"  ✓ Created: {load_results['created']}")
    print(f"  ⚠ Already Existed: {load_results['already_exists']}")
    print(f"  ✗ Errors: {load_results['errors']}")
    
    if load_results['errors'] > 0:
        print(f"\n{'='*80}")
        print("ERRORS")
        print(f"{'='*80}")
        for error_detail in load_results['error_details'][:20]:  # Show first 20 errors
            print(f"  Submittal ID {error_detail['submittal_id']} (Project {error_detail['project_id']}): "
                  f"{error_detail['error']}")
        if len(load_results['error_details']) > 20:
            print(f"\n  ... and {len(load_results['error_details']) - 20} more errors")


def save_results(results: Dict, output_file: str = "logs/draft_tab_submittals_preview.json"):
    """Save results to a JSON file."""
    try:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
            "logs"
        )
        os.makedirs(log_dir, exist_ok=True)
        
        # Convert defaultdict to regular dict for JSON serialization
        results_copy = dict(results)
        results_copy['by_status'] = dict(results['by_status'])
        results_copy['by_type'] = dict(results['by_type'])
        
        filepath = os.path.join(log_dir, "draft_tab_submittals_preview.json")
        with open(filepath, "w") as f:
            json.dump(results_copy, f, indent=2, default=str)
        print(f"\nDetailed results saved to: {filepath}")
    except Exception as e:
        print(f"\nWarning: Could not save results to file: {e}")


def main():
    """Main function to preview and optionally load Draft tab submittals."""
    parser = argparse.ArgumentParser(
        description="Preview and load missing submittals for the 'Draft' tab"
    )
    parser.add_argument(
        '--load',
        action='store_true',
        help='Load missing submittals into the database (default: preview only)'
    )
    args = parser.parse_args()
    
    app = create_app()
    
    with app.app_context():
        procore_client = get_procore_client()
        
        # First, preview to find missing submittals
        results = preview_draft_tab_submittals(procore_client)
        
        if not results:
            print("No results to display.")
            return
        
        print_summary(results)
        save_results(results)
        
        # If --load flag is set, load missing submittals
        if args.load:
            missing_submittals = results.get('missing_submittals', [])
            
            if not missing_submittals:
                print("\n✓ No missing submittals to load!")
                return
            
            # Confirm before loading
            print(f"\n{'='*80}")
            print(f"Ready to load {len(missing_submittals)} missing submittals into the database.")
            print(f"{'='*80}")
            response = input("\nProceed with loading? (yes/no): ").strip().lower()
            
            if response in ['yes', 'y']:
                load_results = load_missing_submittals(procore_client, missing_submittals)
                print_load_summary(load_results)
                
                # Save load results
                try:
                    log_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
                        "logs"
                    )
                    os.makedirs(log_dir, exist_ok=True)
                    filepath = os.path.join(log_dir, "draft_tab_submittals_load_results.json")
                    with open(filepath, "w") as f:
                        json.dump(load_results, f, indent=2, default=str)
                    print(f"\nLoad results saved to: {filepath}")
                except Exception as e:
                    print(f"\nWarning: Could not save load results: {e}")
            else:
                print("\nLoad cancelled.")


if __name__ == "__main__":
    main()

