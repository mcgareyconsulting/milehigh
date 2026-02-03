"""
Script to compare all submittals from Procore API against the database, organized by type.

Specifically checks for submittals with submittal_manager 'Rich Losasso' OR where 'Rich Losasso'
is in ball_in_court, and organizes results by submittal type to identify which ones exist
in Procore but are missing from the database.

Usage:
    python -m app.procore.scripts.compare_draft_submittals
"""

import json
import os
from typing import List, Dict, Optional, Set
from collections import defaultdict

from app import create_app
from app.procore.client import get_procore_client
from app.models import db, ProcoreSubmittal
from app.config import Config as cfg
from app.procore.helpers import parse_ball_in_court_from_submittal


def extract_status(submittal_data: Dict) -> Optional[str]:
    """Extract status from submittal data, handling both dict and string formats."""
    status_obj = submittal_data.get("status")
    if isinstance(status_obj, dict):
        return status_obj.get("name")
    elif isinstance(status_obj, str):
        return status_obj
    return None


def extract_submittal_manager(submittal_data: Dict) -> Optional[str]:
    """Extract submittal_manager from submittal data, handling both dict and string formats."""
    manager_obj = submittal_data.get("submittal_manager") or submittal_data.get("manager")
    if isinstance(manager_obj, dict):
        return manager_obj.get("name") or manager_obj.get("login")
    elif isinstance(manager_obj, str):
        return manager_obj
    return None


def extract_type(submittal_data: Dict) -> Optional[str]:
    """Extract type from submittal data, handling both dict and string formats."""
    type_obj = submittal_data.get("type")
    if isinstance(type_obj, dict):
        return type_obj.get("name")
    elif isinstance(type_obj, str):
        return type_obj
    return None


def normalize_name(name: Optional[str]) -> Optional[str]:
    """Normalize a name for comparison (strip whitespace, case-insensitive)."""
    if not name:
        return None
    return str(name).strip()


def matches_manager(api_manager: Optional[str], target_manager: str) -> bool:
    """Check if API manager name matches target (case-insensitive)."""
    if not api_manager:
        return False
    return normalize_name(api_manager).lower() == normalize_name(target_manager).lower()


def extract_ball_in_court(submittal_data: Dict) -> Optional[str]:
    """Extract ball_in_court from submittal data using the helper function."""
    parsed = parse_ball_in_court_from_submittal(submittal_data)
    if parsed:
        return parsed.get("ball_in_court")
    return None


def is_in_ball_in_court(ball_in_court_value: Optional[str], target_name: str) -> bool:
    """Check if target name is in ball_in_court (handles comma-separated values)."""
    if not ball_in_court_value:
        return False
    
    # Split by comma and check each part
    parts = [part.strip() for part in str(ball_in_court_value).split(',')]
    target_normalized = normalize_name(target_name).lower()
    
    for part in parts:
        if normalize_name(part).lower() == target_normalized:
            return True
    return False


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


def get_submittals_for_project(procore_client, project_id: int, project_name: str, debug: bool = False) -> List[Dict]:
    """Get all submittals for a project."""
    try:
        submittals = procore_client.get_submittals(project_id)
        
        if debug:
            print(f"  DEBUG: Project {project_id} ({project_name}):")
            print(f"    Response type: {type(submittals).__name__}")
            if isinstance(submittals, dict):
                print(f"    Response keys: {list(submittals.keys())}")
                # Check if it's wrapped in a 'data' key
                if 'data' in submittals:
                    submittals = submittals['data']
                    print(f"    Found 'data' key with {len(submittals) if isinstance(submittals, list) else 'non-list'} items")
            elif isinstance(submittals, list):
                print(f"    Returned {len(submittals)} submittals")
                if submittals:
                    # Show sample submittal structure
                    sample = submittals[0]
                    print(f"    Sample submittal keys: {list(sample.keys())[:10] if isinstance(sample, dict) else 'not a dict'}")
                    # Show sample manager and ball_in_court values
                    for i, sub in enumerate(submittals[:3]):
                        manager = extract_submittal_manager(sub)
                        ball_in_court = extract_ball_in_court(sub)
                        print(f"    Submittal {i+1}: manager={manager}, ball_in_court={ball_in_court}")
        
        if not isinstance(submittals, list):
            if isinstance(submittals, dict) and 'data' in submittals:
                submittals = submittals['data']
            else:
                return []
        
        return submittals if isinstance(submittals, list) else []
    except Exception as e:
        print(f"  Warning: Error fetching submittals for project {project_id} ({project_name}): {e}")
        import traceback
        if debug:
            traceback.print_exc()
        return []


def filter_submittals_by_manager_or_ball_in_court(submittals: List[Dict], target_name: str) -> List[Dict]:
    """Filter submittals for matching submittal_manager OR ball_in_court (all statuses and types)."""
    filtered = []
    for submittal in submittals:
        manager = extract_submittal_manager(submittal)
        ball_in_court = extract_ball_in_court(submittal)
        
        # Check if manager matches OR if target is in ball_in_court
        matches = matches_manager(manager, target_name) or is_in_ball_in_court(ball_in_court, target_name)
        
        if matches:
            filtered.append(submittal)
    
    return filtered


def get_db_submittal_ids() -> Set[str]:
    """Get set of all submittal IDs from database."""
    submittals = ProcoreSubmittal.query.all()
    return {str(s.submittal_id) for s in submittals}


def compare_submittals(procore_client, target_name: str = "Rich Losasso") -> Dict:
    """Compare all submittals from Procore API against database, organized by type."""
    print(f"\n{'='*80}")
    print(f"Comparing all submittals with manager or ball_in_court '{target_name}' (organized by type)")
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
        "target_name": target_name,
        "total_projects": len(projects),
        "projects_scanned": 0,
        "projects_with_matches": 0,
        "total_api_submittals": 0,
        "total_db_submittals": len(db_submittal_ids),
        "api_submittals_in_db": 0,
        "api_submittals_missing_from_db": 0,
        "by_type": defaultdict(lambda: {
            "total": 0,
            "in_db": 0,
            "missing_from_db": 0,
            "by_manager": 0,
            "by_ball_in_court": 0,
            "submittals": []
        }),
        "project_details": [],
        "missing_submittals": []
    }
    
    # Scan each project
    print("Scanning projects for submittals...")
    print("-" * 80)
    
    # Debug: Check first few projects to see what we're getting
    debug_mode = True
    total_submittals_fetched = 0
    sample_managers = set()
    sample_ball_in_courts = set()
    
    for i, project in enumerate(projects, 1):
        project_id = project.get("id")
        project_name = project.get("name", "Unknown")
        project_number = project.get("project_number", "Unknown")
        
        if not project_id:
            continue
        
        results["projects_scanned"] += 1
        
        # Get submittals for this project
        submittals = get_submittals_for_project(procore_client, project_id, project_name, debug=(debug_mode and i <= 5))
        total_submittals_fetched += len(submittals)
        
        # Collect sample manager and ball_in_court values for debugging
        if debug_mode and i <= 5 and submittals:
            for sub in submittals[:10]:  # Check first 10 submittals
                manager = extract_submittal_manager(sub)
                ball_in_court = extract_ball_in_court(sub)
                if manager:
                    sample_managers.add(manager)
                if ball_in_court:
                    sample_ball_in_courts.add(ball_in_court)
        
        # Filter for matching manager OR ball_in_court (all statuses and types)
        matching_submittals = filter_submittals_by_manager_or_ball_in_court(submittals, target_name)
        
        if matching_submittals:
            results["projects_with_matches"] += 1
            results["total_api_submittals"] += len(matching_submittals)
            
            project_detail = {
                "project_id": project_id,
                "project_name": project_name,
                "project_number": project_number,
                "submittals": []
            }
            
            for submittal in matching_submittals:
                submittal_id = str(submittal.get("id", ""))
                title = submittal.get("title", "No title")
                status = extract_status(submittal)
                submittal_type = extract_type(submittal)
                manager = extract_submittal_manager(submittal)
                ball_in_court = extract_ball_in_court(submittal)
                
                # Check which field matched
                matched_by_manager = matches_manager(manager, target_name)
                matched_by_ball_in_court = is_in_ball_in_court(ball_in_court, target_name)
                
                # Normalize type for grouping
                type_key = normalize_name(submittal_type) or "Unknown Type"
                
                in_db = submittal_id in db_submittal_ids
                
                # Update type-based statistics
                results["by_type"][type_key]["total"] += 1
                if matched_by_manager:
                    results["by_type"][type_key]["by_manager"] += 1
                if matched_by_ball_in_court:
                    results["by_type"][type_key]["by_ball_in_court"] += 1
                
                if in_db:
                    results["api_submittals_in_db"] += 1
                    results["by_type"][type_key]["in_db"] += 1
                else:
                    results["api_submittals_missing_from_db"] += 1
                    results["by_type"][type_key]["missing_from_db"] += 1
                    results["missing_submittals"].append({
                        "submittal_id": submittal_id,
                        "project_id": project_id,
                        "project_name": project_name,
                        "project_number": project_number,
                        "title": title,
                        "status": status,
                        "type": submittal_type,
                        "submittal_manager": manager,
                        "ball_in_court": ball_in_court,
                        "matched_by_manager": matched_by_manager,
                        "matched_by_ball_in_court": matched_by_ball_in_court
                    })
                
                # Add to type-based list
                results["by_type"][type_key]["submittals"].append({
                    "submittal_id": submittal_id,
                    "project_id": project_id,
                    "project_name": project_name,
                    "project_number": project_number,
                    "title": title,
                    "status": status,
                    "in_database": in_db,
                    "matched_by_manager": matched_by_manager,
                    "matched_by_ball_in_court": matched_by_ball_in_court
                })
                
                project_detail["submittals"].append({
                    "submittal_id": submittal_id,
                    "title": title,
                    "status": status,
                    "type": submittal_type,
                    "submittal_manager": manager,
                    "ball_in_court": ball_in_court,
                    "matched_by_manager": matched_by_manager,
                    "matched_by_ball_in_court": matched_by_ball_in_court,
                    "in_database": in_db
                })
            
            results["project_details"].append(project_detail)
            
            print(f"[{i}/{len(projects)}] {project_name} ({project_number}): "
                  f"Found {len(matching_submittals)} submittal(s) with manager or ball_in_court '{target_name}'")
        
        # Progress indicator
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(projects)} projects scanned...")
    
    # Debug output
    if debug_mode:
        print(f"\n{'='*80}")
        print("DEBUG INFORMATION")
        print(f"{'='*80}")
        print(f"Total submittals fetched from API: {total_submittals_fetched}")
        print(f"Target name: {target_name}")
        print(f"\nSample manager values found (first 5 projects, first 10 submittals each):")
        for mgr in sorted(list(sample_managers))[:20]:
            print(f"  - '{mgr}'")
        print(f"\nSample ball_in_court values found (first 5 projects, first 10 submittals each):")
        for bic in sorted(list(sample_ball_in_courts))[:20]:
            print(f"  - '{bic}'")
        print(f"{'='*80}\n")
    
    return results


def print_summary(results: Dict):
    """Print a formatted summary of the comparison, organized by type."""
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Target Name: {results['target_name']}")
    print(f"Total Projects Scanned: {results['total_projects']}")
    print(f"Projects with Matching Submittals: {results['projects_with_matches']}")
    print(f"\nTotal Submittals in Procore API: {results['total_api_submittals']}")
    print(f"  - Found in Database: {results['api_submittals_in_db']}")
    print(f"  - Missing from Database: {results['api_submittals_missing_from_db']}")
    print(f"\nTotal Submittals in Database: {results['total_db_submittals']}")
    
    # Print breakdown by type
    if results['by_type']:
        print(f"\n{'='*80}")
        print("BREAKDOWN BY TYPE")
        print(f"{'='*80}")
        
        # Sort types by total count (descending)
        sorted_types = sorted(
            results['by_type'].items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )
        
        for type_name, type_data in sorted_types:
            print(f"\n{type_name}:")
            print(f"  Total: {type_data['total']}")
            print(f"    - Matched by Manager: {type_data['by_manager']}")
            print(f"    - Matched by Ball in Court: {type_data['by_ball_in_court']}")
            print(f"  In Database: {type_data['in_db']}")
            print(f"  Missing from Database: {type_data['missing_from_db']}")
    
    if results['missing_submittals']:
        print(f"\n{'='*80}")
        print(f"MISSING SUBMITTALS ({len(results['missing_submittals'])} total)")
        print(f"{'='*80}")
        
        # Group missing submittals by type
        missing_by_type = defaultdict(list)
        for submittal in results['missing_submittals']:
            type_name = normalize_name(submittal.get('type')) or "Unknown Type"
            missing_by_type[type_name].append(submittal)
        
        # Print by type
        for type_name in sorted(missing_by_type.keys()):
            submittals = missing_by_type[type_name]
            print(f"\n--- {type_name} ({len(submittals)} missing) ---")
            for i, submittal in enumerate(submittals, 1):
                print(f"\n  [{i}] Submittal ID: {submittal['submittal_id']}")
                print(f"      Project: {submittal['project_name']} ({submittal['project_number']})")
                print(f"      Title: {submittal['title']}")
                print(f"      Status: {submittal.get('status', 'N/A')}")
                print(f"      Manager: {submittal.get('submittal_manager', 'N/A')}")
                print(f"      Ball in Court: {submittal.get('ball_in_court', 'N/A')}")
                match_info = []
                if submittal.get('matched_by_manager'):
                    match_info.append("Manager")
                if submittal.get('matched_by_ball_in_court'):
                    match_info.append("Ball in Court")
                print(f"      Matched by: {', '.join(match_info) if match_info else 'N/A'}")
    else:
        print("\n✓ All submittals with the specified manager or ball_in_court are present in the database!")


def save_results(results: Dict, output_file: str = "logs/rich_losasso_submittals_comparison.json"):
    """Save results to a JSON file."""
    try:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
            "logs"
        )
        os.makedirs(log_dir, exist_ok=True)
        
        # Convert defaultdict to regular dict for JSON serialization
        results_copy = dict(results)
        results_copy['by_type'] = dict(results['by_type'])
        
        filepath = os.path.join(log_dir, "rich_losasso_submittals_comparison.json")
        with open(filepath, "w") as f:
            json.dump(results_copy, f, indent=2, default=str)
        print(f"\nDetailed results saved to: {filepath}")
    except Exception as e:
        print(f"\nWarning: Could not save results to file: {e}")


def main():
    """Main function to compare all submittals by type."""
    app = create_app()
    
    with app.app_context():
        procore_client = get_procore_client()
        target_name = "Rich Losasso"
        
        results = compare_submittals(procore_client, target_name)
        
        if results:
            print_summary(results)
            save_results(results)
        else:
            print("No results to display.")


if __name__ == "__main__":
    main()

