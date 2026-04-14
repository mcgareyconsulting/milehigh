"""
@milehigh-header
schema_version: 1
purpose: Shared utilities for Procore webhook management scripts (project listing, delivery inspection, operation logging).
exports:
  get_unique_projects: Query distinct project IDs and numbers from the submittals table.
  log_operation: Append a JSON-lines log entry for a webhook management action.
  get_webhook_triggers: Fetch all triggers for a specific webhook via the Procore client.
  get_recent_deliveries: Retrieve webhook deliveries within a rolling N-day window.
imports_from: [json, os, datetime, app.models, app.procore.client, app.config]
imported_by: [app/procore/scripts/check.py, app/procore/scripts/create.py, app/procore/scripts/delete.py, app/procore/scripts/ensure_webhooks.py, app/procore/scripts/view_deliveries.py]
invariants:
  - get_unique_projects skips rows with non-integer project IDs rather than raising.
  - log_operation creates the logs/ directory if it does not exist.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Shared utilities for Procore webhook management scripts.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.models import db, Submittals
from app.procore.client import get_procore_client
from app.config import Config as cfg


def get_unique_projects(include_name: bool = False) -> List[Tuple]:
    """
    Get unique project IDs and project numbers from procore_submittals table.
    
    Args:
        include_name: If True, returns (project_id, project_number, project_name)
                       If False, returns (project_id, project_number)
    
    Returns:
        List of project tuples
    """
    if include_name:
        results = db.session.query(
            Submittals.procore_project_id,
            Submittals.project_number,
            Submittals.project_name
        ).distinct().all()
        
        projects = []
        for project_id, project_number, project_name in results:
            if project_id:
                try:
                    project_id_int = int(project_id)
                    projects.append((project_id_int, project_number, project_name))
                except (ValueError, TypeError):
                    print(f"Warning: Invalid project_id {project_id}")
        return projects
    else:
        results = db.session.query(
            Submittals.procore_project_id,
            Submittals.project_number
        ).distinct().all()
        
        projects = []
        for project_id, project_number in results:
            if project_id:
                try:
                    project_id_int = int(project_id)
                    projects.append((project_id_int, project_number))
                except (ValueError, TypeError):
                    print(f"Warning: Invalid project_id {project_id} for project_number {project_number}")
        return projects


def log_operation(log_file: str, action: str, project_id: int, project_number: Optional[str], 
                 data: Dict, status: str = "success"):
    """Log webhook operation response to file."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "project_id": project_id,
        "project_number": project_number,
        "status": status,
        "data": data
    }
    
    # Ensure logs directory exists
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_path = os.path.join(log_dir, log_file)
    
    # Append to log file (JSON Lines format)
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"[{status.upper()}] {action} - Project {project_id} ({project_number}): {json.dumps(data)[:100]}")



def get_webhook_triggers(procore_client, project_id: int, hook_id: int) -> List[Dict]:
    """Get all triggers for a specific webhook."""
    try:
        triggers = procore_client.get_webhook_triggers(project_id, hook_id)
        return triggers if triggers else []
    except Exception as e:
        print(f"Error getting triggers for hook {hook_id} in project {project_id}: {e}")
        return []


def get_recent_deliveries(procore_client, project_id: int, hook_id: int, 
                         days_back: int = 7) -> List[Dict]:
    """Get recent webhook deliveries for a specific hook within the last N days."""
    try:
        deliveries = procore_client.get_webhook_deliveries(
            cfg.PROD_PROCORE_COMPANY_ID, project_id, hook_id
        )
        
        if not deliveries:
            return []
        
        # Filter by date (last N days)
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        recent_deliveries = []
        for delivery in deliveries:
            # Parse delivery timestamp
            created_at_str = delivery.get("created_at")
            if created_at_str:
                try:
                    # Parse ISO format timestamp
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    # Convert to naive datetime for comparison
                    if created_at.tzinfo:
                        created_at_naive = created_at.replace(tzinfo=None)
                    else:
                        created_at_naive = created_at
                    if created_at_naive >= cutoff_date:
                        recent_deliveries.append(delivery)
                except (ValueError, AttributeError):
                    # If we can't parse date, include it anyway
                    recent_deliveries.append(delivery)
        
        # Sort by most recent first
        recent_deliveries.sort(
            key=lambda x: x.get("created_at", ""), 
            reverse=True
        )
        
        return recent_deliveries
        
    except Exception as e:
        print(f"Error getting deliveries for hook {hook_id}: {e}")
        return []

