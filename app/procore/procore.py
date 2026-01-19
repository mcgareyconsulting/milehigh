import logging
import re
import json
import os
import hashlib
import requests
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from requests.exceptions import ConnectionError, Timeout
from urllib3.exceptions import ProtocolError
from app.config import Config as cfg
from app.models import db, Job, ProcoreSubmittal, SubmittalEvents
from app.trello.api import add_procore_link
from app.procore.procore_auth import get_access_token
from app.procore.client import get_procore_client
from app.procore.helpers import parse_ball_in_court_from_submittal


logger = logging.getLogger(__name__)


def _create_submittal_payload_hash(action, submittal_id, payload):
    """
    Create a hash for the submittal event payload to prevent duplicates.
    
    Args:
        action: The action type (e.g., 'created', 'updated')
        submittal_id: The submittal ID
        payload: The payload dictionary
        
    Returns:
        str: SHA-256 hash of the payload
    """
    # Normalize the payload by sorting keys and converting to JSON
    # This ensures consistent hashing regardless of key order
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    
    # Create hash string from action + submittal_id + payload
    hash_string = f"{action}:{submittal_id}:{payload_json}"
    
    # Generate SHA-256 hash
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()


def _request_json(url, headers, params=None):
    """
    Wrapper around requests.get that adds logging and error handling.
    Returns JSON data or None if the request fails.
    """
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Procore request failed: url=%s params=%s", url, params)
        return None

    try:
        data = response.json()
    except ValueError:
        logger.error("Procore response is not valid JSON: url=%s params=%s body=%r", url, params, response.text[:500])
        return None

    if isinstance(data, dict) and data.get("errors"):
        logger.error("Procore returned errors: url=%s params=%s errors=%s", url, params, data.get("errors"))
        return None

    return data


def _normalize_title(value):
    if not value:
        return ""
    normalized = re.sub(r"\s*-\s*", "-", value.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized

# def procore_authorization():
#     url = "https://login.procore.com/oauth/token/"
#     headers = {
#         "Content-Type": "application/x-www-form-urlencoded",
#     }
#     body = {
#         "grant_type": "authorization_code",
#         "code": cfg.PROD_PROCORE_AUTH_CODE,
#         "client_id": cfg.PROD_PROCORE_CLIENT_ID,
#         "client_secret": cfg.PROD_PROCORE_CLIENT_SECRET,
#         "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
#     }
#     response = requests.post(url, data=body)
#     print(response.json())
#     return response.json()

# Get Companies List
def get_companies_list():
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.0/companies"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    companies = _request_json(url, headers=headers) or []
    if not companies:
        logger.warning("No companies returned from Procore")
        return None
    company_id = companies[0]["id"]
    return company_id

# count num projects by company id
def count_projects_by_company_id(company_id):
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects?company_id={company_id}"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Procore-Company-Id": str(company_id),
    }
    projects = _request_json(url, headers=headers) or []
    return len(projects)


# Get Projects by Company ID
def get_projects_by_company_id(company_id, project_number):
    '''
    Get projects by company ID and project number
    '''
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects?company_id={company_id}"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Procore-Company-Id": str(company_id),
    }
    projects = _request_json(url, headers=headers) or []
    for project in projects:
        if project["project_number"] == str(project_number):
            return project["id"]
    return None

# Function to get project id by project name
def get_project_id_by_project_name(project_name):
    # get procore client
    procore = get_procore_client()
    projects = procore.get_projects(cfg.PROD_PROCORE_COMPANY_ID)
    print(len(projects))
    for project in projects:
        if project["name"] == project_name:
            print(project["project_number"], project["name"], project["id"])
            return project["id"]
    return None

def parse_and_log_submittal_data(submittal_data: dict, project_id: int, submittal_id: int, source: str = "webhook"):
    """
    Parse submittal data into a clean, structured format and log it for easy visualization.
    
    Args:
        submittal_data: Raw submittal data from Procore API
        project_id: Procore project ID
        submittal_id: Procore submittal ID
        source: Source of the data (e.g., "webhook", "api")
    
    Returns:
        dict: Parsed submittal data in a structured format
    """
    if not isinstance(submittal_data, dict):
        logger.warning(f"Cannot parse submittal data - not a dict: {type(submittal_data)}")
        return None
    
    # Extract key fields in a structured way
    parsed = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "project_id": project_id,
        "submittal_id": submittal_id,
        "summary": {},
        "fields": {},
        "nested_objects": {},
        "raw_data_keys": list(submittal_data.keys()) if isinstance(submittal_data, dict) else []
    }
    
    # Extract common fields
    def extract_value(obj, default=None):
        """Extract value from object (handles dict, string, or None)"""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get("name") or obj.get("id") or obj.get("login") or str(obj)
        if isinstance(obj, str):
            return obj.strip() if obj.strip() else default
        return str(obj) if obj else default
    
    # Summary fields (most important)
    parsed["summary"] = {
        "title": submittal_data.get("title"),
        "status": extract_value(submittal_data.get("status")),
        "type": extract_value(submittal_data.get("type")),
        "ball_in_court": extract_value(submittal_data.get("ball_in_court")),
        "submittal_manager": extract_value(submittal_data.get("submittal_manager") or submittal_data.get("manager")),
        "specification_section": extract_value(submittal_data.get("specification_section")),
        "created_at": submittal_data.get("created_at"),
        "updated_at": submittal_data.get("updated_at"),
    }
    
    # Parse ball_in_court using existing helper
    ball_parsed = parse_ball_in_court_from_submittal(submittal_data)
    if ball_parsed:
        parsed["summary"]["ball_in_court_parsed"] = ball_parsed.get("ball_in_court")
        parsed["summary"]["ball_in_court_details"] = ball_parsed
    
    # Extract all top-level fields
    for key, value in submittal_data.items():
        if key in ["status", "type", "ball_in_court", "submittal_manager", "manager", "specification_section"]:
            # Already in summary, skip
            continue
        
        if isinstance(value, (str, int, float, bool, type(None))):
            parsed["fields"][key] = value
        elif isinstance(value, dict):
            # Store nested objects separately
            parsed["nested_objects"][key] = {
                "type": "object",
                "keys": list(value.keys()) if isinstance(value, dict) else [],
                "sample": {k: v for k, v in list(value.items())[:5]}  # First 5 items
            }
        elif isinstance(value, list):
            parsed["nested_objects"][key] = {
                "type": "array",
                "length": len(value),
                "item_type": type(value[0]).__name__ if len(value) > 0 else "empty",
                "sample": value[0] if len(value) > 0 and isinstance(value[0], (str, int, float, bool)) else None
            }
    
    # Log to file
    try:
        log_dir = cfg.SNAPSHOTS_DIR
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "procore_submittal_data.log")
        
        with open(log_file, "a") as f:
            f.write(json.dumps(parsed, indent=2) + "\n" + "-" * 80 + "\n")
        
        logger.info(f"Logged parsed submittal data to {log_file}")
    except Exception as e:
        logger.error(f"Failed to log submittal data: {str(e)}", exc_info=True)
    
    return parsed


# Get Submittal by ID
def get_submittal_by_id(project_id, submittal_id):
    procore = get_procore_client()
    submittal = procore.get_submittal_by_id(project_id, submittal_id)
    return submittal

# Get Submittals by Project ID and Identifier
def get_submittals_by_project_id(project_id, identifier):
    """Get submittals by project ID and identifier"""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    submittals = _request_json(url, headers=headers)
    if not isinstance(submittals, list):
        logger.warning("Unexpected submittals payload for project_id=%s identifier=%s: %r", project_id, identifier, submittals)
        return []
    normalized_identifier = (identifier or "").strip().lower()
    return [
        s for s in submittals
        if normalized_identifier in _normalize_title(s.get("title", ""))
        and s.get("type", {}).get("name") == "For Construction"
    ]


# Get Workflow Data by Project ID and Submittal ID
def get_workflow_data(project_id, submittal_id):
    """Fetch workflow data for a given submittal"""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/workflow_data"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    workflow_data = _request_json(url, headers=headers)
    if workflow_data is None:
        logger.warning("Missing workflow data for project_id=%s submittal_id=%s", project_id, submittal_id)
        return {}
    return workflow_data


# Get Final PDF Viewers by Project ID and Submittals
def get_final_pdf_viewers(project_id, submittals):
    """Extract viewer URLs for 'Final PDF Pack' responses"""
    final_results = []

    for sub in submittals:
        submittal_id = sub["id"]
        title = sub.get("title")

        # Step 1: Find response name "Final PDF Pack"
        responses = sub.get("last_distributed_submittal", {}).get("distributed_responses", [])
        approver_ids = [
            r.get("submittal_approver_id")
            for r in responses if r.get("response_name") == "Final PDF Pack"
        ]
        if not approver_ids:
            continue

        # Step 2: Get workflow data
        workflow_data = get_workflow_data(project_id, submittal_id)

        # Step 3: Match approver_id → attachment → viewer_url
        attachments = workflow_data.get("attachments") if isinstance(workflow_data, dict) else []
        for att in attachments or []:
            if att.get("approver_id") in approver_ids:
                viewer_url = att.get("viewer_url")
                if viewer_url:
                    full_viewer_url = f"https://app.procore.com{viewer_url}"
                    final_results.append({
                        "title": title,
                        "submittal_id": submittal_id,
                        "approver_id": att.get("approver_id"),
                        "filename": att.get("name"),
                        "viewer_url": full_viewer_url,
                    })

    return final_results

def get_webhook_deliveries(company_id, project_id):
    procore = get_procore_client()

    # get webhook_id based on project_id assuming 1 hook
    webhooks = procore.list_project_webhooks(project_id, 'mile-high-metal-works')
    if not webhooks:
        logger.error("No Procore webhooks found for project_id=%s", project_id)
        return None
    webhook_id = webhooks[0]["id"]
    if not webhook_id:
        logger.error("No Procore webhook_id found for project_id=%s", project_id)
        return None
    return procore.get_deliveries(company_id, project_id, webhook_id)


def handle_submittal_update(project_id, submittal_id):
    """
    Compare ball_in_court, status, title, and submittal_manager from submittal webhook data against DB record.
    
    Args:
        project_id: The Procore project ID
        submittal_id: The submittal ID (resource_id from webhook)
        
    Returns:
        tuple: (procore_submittal, ball_in_court, approvers, status, title, submittal_manager) or None if parsing fails
        - procore_submittal: ProcoreSubmittal DB record or None if not found
        - ball_in_court: str or None - User who has the ball in court
        - approvers: list - List of approver data
        - status: str or None - Status of the submittal from Procore
        - title: str or None - Title of the submittal from Procore
        - submittal_manager: str or None - Submittal manager from Procore
    """
    # Collect submittal data and pass to parser function
    submittal = get_submittal_by_id(project_id, submittal_id)
    if not isinstance(submittal, dict):
        return None
    
    # Parse and log submittal data for visualization
    try:
        parse_and_log_submittal_data(submittal, project_id, submittal_id, source="webhook_update")
    except Exception as parse_error:
        logger.warning(f"Failed to parse/log submittal data (non-fatal): {parse_error}")
    
    parsed = parse_ball_in_court_from_submittal(submittal)
    if parsed is None:
        return None
    
    ball_in_court = parsed.get("ball_in_court")
    approvers = parsed.get("approvers", [])
    
    # Extract status from submittal data
    # Status might be a string or nested in a dict with 'name' key
    status_obj = submittal.get("status")
    if isinstance(status_obj, dict):
        status = status_obj.get("name")
    elif isinstance(status_obj, str):
        status = status_obj
    else:
        status = None
    
    # Normalize status to string or None
    status = str(status).strip() if status else None
    
    # Extract title
    title = submittal.get("title")
    title = str(title).strip() if title else None
    
    # Extract submittal_manager (if available)
    submittal_manager_obj = submittal.get("submittal_manager") or submittal.get("manager")
    if isinstance(submittal_manager_obj, dict):
        submittal_manager = submittal_manager_obj.get("name") or submittal_manager_obj.get("login")
    elif isinstance(submittal_manager_obj, str):
        submittal_manager = submittal_manager_obj
    else:
        submittal_manager = None
    submittal_manager = str(submittal_manager).strip() if submittal_manager else None
    
    # Look up the DB record
    procore_submittal = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
    
    # Always return a tuple, even if procore_submittal is None
    return procore_submittal, ball_in_court, approvers, status, title, submittal_manager


def get_project_info(project_id):
    """
    Get project information (name and number) by project ID.
    
    Args:
        project_id: Procore project ID
        
    Returns:
        dict with 'name' and 'project_number' keys, or None if not found
    """
    try:
        procore = get_procore_client()
        projects = procore.get_projects(cfg.PROD_PROCORE_COMPANY_ID)
        for project in projects:
            if project.get("id") == project_id:
                return {
                    "name": project.get("name"),
                    "project_number": project.get("project_number")
                }
        logger.warning(f"Project {project_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error getting project info for project {project_id}: {e}", exc_info=True)
        return None


def create_submittal_from_webhook(project_id, submittal_id):
    """
    Create a new ProcoreSubmittal record in the database from a webhook create event.
    
    Args:
        project_id: Procore project ID
        submittal_id: Procore submittal ID (resource_id from webhook)
        
    Returns:
        tuple: (created: bool, record: ProcoreSubmittal or None, error_message: str or None)
    """
    try:
        logger.info(f"Starting create_submittal_from_webhook for submittal {submittal_id}, project {project_id}")
        
        # Check if submittal already exists
        existing = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
        if existing:
            logger.info(f"Submittal {submittal_id} already exists in database, skipping creation")
            return False, existing, None
        
        logger.info(f"Fetching submittal data from Procore API for submittal {submittal_id}")
        # Get submittal data from Procore API
        submittal_data = get_submittal_by_id(project_id, submittal_id)
        if not isinstance(submittal_data, dict):
            error_msg = f"Failed to fetch submittal data from Procore API - got {type(submittal_data)} instead of dict"
            logger.error(f"{error_msg} for submittal {submittal_id}")
            return False, None, error_msg
        
        # Parse and log submittal data for visualization
        try:
            parse_and_log_submittal_data(submittal_data, project_id, submittal_id, source="webhook_create")
        except Exception as parse_error:
            logger.warning(f"Failed to parse/log submittal data (non-fatal): {parse_error}")
        
        logger.info(f"Fetching project info for project {project_id}")
        # Get project information
        project_info = get_project_info(project_id)
        if not project_info:
            error_msg = f"Failed to fetch project info for project {project_id}"
            logger.error(f"{error_msg}")
            return False, None, error_msg
        
        logger.info(f"Successfully fetched project info: {project_info.get('name')} ({project_info.get('project_number')})")
        
        # Parse ball_in_court from submittal data
        parsed = parse_ball_in_court_from_submittal(submittal_data)
        ball_in_court = parsed.get("ball_in_court") if parsed else None
        
        # Extract status
        status_obj = submittal_data.get("status")
        if isinstance(status_obj, dict):
            status = status_obj.get("name")
        elif isinstance(status_obj, str):
            status = status_obj
        else:
            status = None
        status = str(status).strip() if status else None
        
        # Extract type
        type_obj = submittal_data.get("type")
        if isinstance(type_obj, dict):
            submittal_type = type_obj.get("name")
        elif isinstance(type_obj, str):
            submittal_type = type_obj
        else:
            submittal_type = None
        submittal_type = str(submittal_type).strip() if submittal_type else None
        
        # Extract title
        title = submittal_data.get("title")
        title = str(title).strip() if title else None
        
        # Extract submittal_manager (if available)
        submittal_manager_obj = submittal_data.get("submittal_manager") or submittal_data.get("manager")
        if isinstance(submittal_manager_obj, dict):
            submittal_manager = submittal_manager_obj.get("name") or submittal_manager_obj.get("login")
        elif isinstance(submittal_manager_obj, str):
            submittal_manager = submittal_manager_obj
        else:
            submittal_manager = None
        submittal_manager = str(submittal_manager).strip() if submittal_manager else None
        
        logger.info(f"Creating new ProcoreSubmittal record with title: {title}")

        # Extract created_at from Procore API if available
        procore_created_at = None
        created_at_str = submittal_data.get("created_at")
        logger.info(f"Extracting created_at from API: {created_at_str}")
        if created_at_str:
            try:
                # Parse ISO format timestamp (handles Z suffix and timezone offsets)
                procore_created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                # Convert to naive datetime (remove timezone info)
                if procore_created_at.tzinfo:
                    procore_created_at = procore_created_at.replace(tzinfo=None)
                logger.info(f"Parsed procore_created_at: {procore_created_at}")
            except (ValueError, AttributeError) as e:
                logger.warning(f"Could not parse created_at '{created_at_str}' from Procore API: {e}")
                procore_created_at = None
        
        # Fallback to current time if not available from API
        if not procore_created_at:
            logger.warning(f"Using fallback datetime.utcnow() because procore_created_at is None")
            procore_created_at = datetime.utcnow()
        
        # Double-check it doesn't exist (race condition protection)
        # Another thread/request might have created it between our initial check and now
        existing_check = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
        if existing_check:
            logger.info(
                f"Submittal {submittal_id} was created by another process between initial check and commit. "
                f"Returning existing record."
            )
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
            created_at=procore_created_at,
            last_updated=datetime.utcnow()
        )
        
        db.session.add(new_submittal)
        logger.info(f"Added submittal to session, committing to database...")
        
        try:
            db.session.commit()
            logger.info(f"Successfully committed submittal to database")
        except IntegrityError as integrity_error:
            # Handle unique constraint violations (if another thread created it during commit)
            logger.warning(
                f"Unique constraint violation during commit for submittal {submittal_id}. "
                f"This likely means another process created it concurrently. Rolling back and fetching existing record."
            )
            db.session.rollback()
            # Fetch the record that was created by the other process
            existing_after_error = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
            if existing_after_error:
                logger.info(f"Found existing record created by concurrent process, returning it")
                return False, existing_after_error, None
            else:
                # Unexpected: constraint violation but no record found
                error_msg = f"Unique constraint violation but no existing record found: {integrity_error}"
                logger.error(error_msg)
                return False, None, error_msg
        except Exception as commit_error:
            # Re-raise other commit errors after logging
            logger.error(f"Unexpected error during commit: {commit_error}", exc_info=True)
            raise
        
        # Create submittal event for creation
        try:
            action = "created"
            payload = {
                "submittal_id": str(submittal_id),
                "project_id": str(project_id),
                "title": title,
                "status": status,
                "type": submittal_type,
                "ball_in_court": str(ball_in_court).strip() if ball_in_court else None,
                "submittal_manager": submittal_manager,
                "project_name": project_info.get("name"),
                "project_number": str(project_info.get("project_number", "")).strip() or None
            }
            payload_hash = _create_submittal_payload_hash(action, str(submittal_id), payload)
            
            # Check if event already exists
            existing_event = SubmittalEvents.query.filter_by(payload_hash=payload_hash).first()
            if not existing_event:
                event = SubmittalEvents(
                    submittal_id=str(submittal_id),
                    action=action,
                    payload=payload,
                    payload_hash=payload_hash,
                    source='Procore'
                )
                db.session.add(event)
                db.session.commit()
                logger.info(f"Created SubmittalEvent for submittal {submittal_id} creation")
            else:
                logger.debug(f"SubmittalEvent already exists for submittal {submittal_id} creation, skipping")
        except Exception as event_error:
            # Log but don't fail the creation if event creation fails
            logger.warning(f"Failed to create SubmittalEvent for submittal {submittal_id} creation: {event_error}", exc_info=True)
        
        logger.info(
            f"Created new submittal record: submittal_id={submittal_id}, "
            f"project_id={project_id}, title={title}"
        )
        
        return True, new_submittal, None
        
    except (ConnectionError, ProtocolError, Timeout) as e:
        # Connection errors - classify and provide better error message
        # Note: The API client already retries these, so if we get here, all retries failed
        error_type = type(e).__name__
        error_msg = (
            f"Connection error while creating submittal {submittal_id}: {error_type} - {str(e)}. "
            f"This may be a temporary network issue. The webhook will be retried on the next update event."
        )
        logger.error(error_msg, exc_info=True)
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(f"Error during rollback: {rollback_error}", exc_info=True)
        return False, None, error_msg
    except Exception as e:
        # Other errors - classify and log
        error_type = type(e).__name__
        error_msg = f"Error creating submittal {submittal_id} from webhook: {error_type} - {str(e)}"
        logger.error(error_msg, exc_info=True)
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(f"Error during rollback: {rollback_error}", exc_info=True)
        return False, None, error_msg


def _check_submitter_pending_in_workflow(approvers):
    """
    Check if the submitter (workflow_group_number 0) appears as a pending approver
    in the next workflow group that has pending approvers.
    The "next workflow group" is determined by finding the workflow group with the
    smallest workflow_group_number > 0 that has at least one pending approver.
    Only checks the next pending approver in line for urgency bump functionality.
    
    Args:
        approvers: List of approver dictionaries from submittal data
        
    Returns:
        bool: True if submitter appears as pending in the next workflow group with pending approvers
    """
    print(f"[SUBMITTER CHECK] Starting check with {len(approvers) if approvers else 0} approvers")
    logger.info(f"[SUBMITTER CHECK] Starting check with {len(approvers) if approvers else 0} approvers")
    
    if not approvers or not isinstance(approvers, list):
        print(f"[SUBMITTER CHECK] No approvers list or invalid type")
        logger.info(f"[SUBMITTER CHECK] No approvers list or invalid type")
        return False
    
    # Find the submitter (workflow_group_number 0)
    submitter = None
    print(f"[SUBMITTER CHECK] Searching for submitter (workflow_group_number 0)...")
    logger.info(f"[SUBMITTER CHECK] Searching for submitter (workflow_group_number 0)...")
    
    for approver in approvers:
        if not isinstance(approver, dict):
            continue
        workflow_group = approver.get("workflow_group_number")
        print(f"[SUBMITTER CHECK] Checking approver with workflow_group_number={workflow_group}")
        logger.info(f"[SUBMITTER CHECK] Checking approver with workflow_group_number={workflow_group}")
        
        if workflow_group == 0:
            user = approver.get("user")
            if user and isinstance(user, dict):
                submitter = {
                    "name": user.get("name"),
                    "login": user.get("login")
                }
                print(f"[SUBMITTER CHECK] Found submitter: name='{submitter.get('name')}', login='{submitter.get('login')}'")
                logger.info(f"[SUBMITTER CHECK] Found submitter: name='{submitter.get('name')}', login='{submitter.get('login')}'")
            break
    
    if not submitter:
        print(f"[SUBMITTER CHECK] No submitter found (workflow_group_number 0 not found)")
        logger.info(f"[SUBMITTER CHECK] No submitter found (workflow_group_number 0 not found)")
        return False
    
    # Find the next workflow group that has at least one pending approver
    # First, collect all workflow groups > 0 that have pending approvers
    pending_workflow_groups = set()
    for approver in approvers:
        if not isinstance(approver, dict):
            continue
        
        workflow_group = approver.get("workflow_group_number")
        if workflow_group is None or workflow_group == 0:
            continue  # Skip submitter or approvers without workflow_group_number
        
        # Check if this approver is pending
        response = approver.get("response", {})
        if isinstance(response, dict):
            response_name = response.get("name", "").strip()
            if response_name.lower() == "pending":
                pending_workflow_groups.add(workflow_group)
                print(f"[SUBMITTER CHECK] Found pending approver in workflow_group_number={workflow_group}")
                logger.info(f"[SUBMITTER CHECK] Found pending approver in workflow_group_number={workflow_group}")
    
    if not pending_workflow_groups:
        print(f"[SUBMITTER CHECK] No pending workflow groups found")
        logger.info(f"[SUBMITTER CHECK] No pending workflow groups found")
        return False
    
    # Find the minimum workflow group number (the next one in line)
    next_workflow_group = min(pending_workflow_groups)
    print(f"[SUBMITTER CHECK] Next pending workflow group to check: {next_workflow_group}")
    logger.info(f"[SUBMITTER CHECK] Next pending workflow group to check: {next_workflow_group}")
    
    # Check if submitter appears as pending in the NEXT workflow group only
    print(f"[SUBMITTER CHECK] Checking if submitter appears as pending in workflow_group_number={next_workflow_group}...")
    logger.info(f"[SUBMITTER CHECK] Checking if submitter appears as pending in workflow_group_number={next_workflow_group}...")
    
    for approver in approvers:
        if not isinstance(approver, dict):
            continue
        
        workflow_group = approver.get("workflow_group_number")
        # Only check approvers in the next workflow group
        if workflow_group != next_workflow_group:
            continue
        
        print(f"[SUBMITTER CHECK] Checking approver at workflow_group_number={workflow_group}")
        logger.info(f"[SUBMITTER CHECK] Checking approver at workflow_group_number={workflow_group}")
        
        # Check if response is "Pending"
        response = approver.get("response", {})
        if not isinstance(response, dict):
            print(f"[SUBMITTER CHECK]   Response is not a dict, skipping")
            logger.info(f"[SUBMITTER CHECK]   Response is not a dict, skipping")
            continue
        
        response_name = response.get("name", "").strip()
        print(f"[SUBMITTER CHECK]   Response name: '{response_name}'")
        logger.info(f"[SUBMITTER CHECK]   Response name: '{response_name}'")
        
        if response_name.lower() != "pending":
            print(f"[SUBMITTER CHECK]   Response is not 'Pending', skipping")
            logger.info(f"[SUBMITTER CHECK]   Response is not 'Pending', skipping")
            continue
        
        # Check if user matches submitter
        user = approver.get("user")
        if not user or not isinstance(user, dict):
            print(f"[SUBMITTER CHECK]   User is not a dict, skipping")
            logger.info(f"[SUBMITTER CHECK]   User is not a dict, skipping")
            continue
        
        approver_name = user.get("name")
        approver_login = user.get("login")
        print(f"[SUBMITTER CHECK]   Approver user: name='{approver_name}', login='{approver_login}'")
        logger.info(f"[SUBMITTER CHECK]   Approver user: name='{approver_name}', login='{approver_login}'")
        
        # Match by name or login
        name_match = (submitter.get("name") and approver_name and 
                     submitter.get("name").lower() == approver_name.lower())
        login_match = (submitter.get("login") and approver_login and 
                      submitter.get("login").lower() == approver_login.lower())
        
        print(f"[SUBMITTER CHECK]   Name match: {name_match}, Login match: {login_match}")
        logger.info(f"[SUBMITTER CHECK]   Name match: {name_match}, Login match: {login_match}")
        
        if name_match or login_match:
            print(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('name')}' appears as pending at workflow_group_number={workflow_group}")
            logger.info(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('name')}' appears as pending at workflow_group_number={workflow_group}")
            return True
    
    # No match found in the next workflow group
    print(f"[SUBMITTER CHECK] ✗ No match found: Submitter does not appear as pending in workflow_group_number={next_workflow_group}")
    logger.info(f"[SUBMITTER CHECK] ✗ No match found: Submitter does not appear as pending in workflow_group_number={next_workflow_group}")
    return False


def _bump_order_number_to_decimal(record, submittal_id, ball_in_court_value):
    """
    Convert an integer order number to an urgent decimal (e.g., 6 -> 0.6).
    Handles collision detection and finds the next available decimal.
    
    Args:
        record: ProcoreSubmittal DB record
        submittal_id: Submittal ID for logging
        ball_in_court_value: Current ball_in_court value for collision detection
        
    Returns:
        bool: True if order number was bumped, False otherwise
    """
    print(f"[ORDER BUMP] Starting bump check for submittal {submittal_id}")
    logger.info(f"[ORDER BUMP] Starting bump check for submittal {submittal_id}")
    
    if record.order_number is None:
        print(f"[ORDER BUMP] Order number is None, cannot bump")
        logger.info(f"[ORDER BUMP] Order number is None, cannot bump")
        return False
    
    current_order = record.order_number
    print(f"[ORDER BUMP] Current order number: {current_order} (type: {type(current_order)})")
    logger.info(f"[ORDER BUMP] Current order number: {current_order} (type: {type(current_order)})")
    
    # Check if order_number is an integer >= 1
    is_integer = isinstance(current_order, (int, float)) and current_order >= 1 and current_order == int(current_order)
    print(f"[ORDER BUMP] Is integer >= 1: {is_integer}")
    logger.info(f"[ORDER BUMP] Is integer >= 1: {is_integer}")
    
    if not is_integer:
        print(f"[ORDER BUMP] Order number is not an integer >= 1, cannot bump")
        logger.info(f"[ORDER BUMP] Order number is not an integer >= 1, cannot bump")
        return False
    
    # Convert to urgent decimal (e.g., 6 -> 0.6)
    target_decimal = current_order / 10.0
    print(f"[ORDER BUMP] Target decimal: {target_decimal} (from {int(current_order)} / 10.0)")
    logger.info(f"[ORDER BUMP] Target decimal: {target_decimal} (from {int(current_order)} / 10.0)")
    
    # Find all existing order numbers for this ball_in_court that are < 1
    print(f"[ORDER BUMP] Checking for collisions with ball_in_court='{ball_in_court_value}'")
    logger.info(f"[ORDER BUMP] Checking for collisions with ball_in_court='{ball_in_court_value}'")
    
    existing_urgent_orders = db.session.query(ProcoreSubmittal.order_number).filter(
        ProcoreSubmittal.ball_in_court == ball_in_court_value,
        ProcoreSubmittal.submittal_id != submittal_id,  # Exclude current submittal
        ProcoreSubmittal.order_number < 1,
        ProcoreSubmittal.order_number.isnot(None)
    ).all()
    existing_urgent_orders = [float(o[0]) for o in existing_urgent_orders if o[0] is not None]
    
    print(f"[ORDER BUMP] Found {len(existing_urgent_orders)} existing urgent orders: {existing_urgent_orders}")
    logger.info(f"[ORDER BUMP] Found {len(existing_urgent_orders)} existing urgent orders: {existing_urgent_orders}")
    
    # Find next available decimal that is more urgent (smaller) than any collision
    new_order = target_decimal
    if target_decimal in existing_urgent_orders:
        print(f"[ORDER BUMP] Collision detected! {target_decimal} already exists")
        logger.info(f"[ORDER BUMP] Collision detected! {target_decimal} already exists")
        
        # Collision detected - find next available smaller decimal
        if existing_urgent_orders:
            smallest_existing = min(existing_urgent_orders)
            candidate = smallest_existing / 2.0
            print(f"[ORDER BUMP] Starting collision resolution: smallest_existing={smallest_existing}, initial candidate={candidate}")
            logger.info(f"[ORDER BUMP] Starting collision resolution: smallest_existing={smallest_existing}, initial candidate={candidate}")
            
            # Keep halving until we find a value that's not in the list
            max_iterations = 10  # Prevent infinite loops
            iteration = 0
            while candidate in existing_urgent_orders and candidate > 0.001 and iteration < max_iterations:
                candidate = candidate / 2.0
                iteration += 1
                print(f"[ORDER BUMP]   Iteration {iteration}: candidate={candidate}")
                logger.info(f"[ORDER BUMP]   Iteration {iteration}: candidate={candidate}")
            
            # If we still have a collision after iterations, use a fixed small value
            if candidate in existing_urgent_orders or candidate <= 0:
                candidate = 0.01
                print(f"[ORDER BUMP]   Using fallback value: {candidate}")
                logger.info(f"[ORDER BUMP]   Using fallback value: {candidate}")
            
            new_order = candidate
        else:
            # No existing urgent orders, but target_decimal is somehow in the list (shouldn't happen)
            new_order = target_decimal / 2.0
            print(f"[ORDER BUMP] Edge case: using {new_order}")
            logger.info(f"[ORDER BUMP] Edge case: using {new_order}")
    else:
        print(f"[ORDER BUMP] No collision, using target decimal: {new_order}")
        logger.info(f"[ORDER BUMP] No collision, using target decimal: {new_order}")
    
    record.order_number = new_order
    print(f"[ORDER BUMP] ✓ BUMPED: {int(current_order)} -> {new_order} for submittal {submittal_id}")
    logger.info(f"[ORDER BUMP] ✓ BUMPED: {int(current_order)} -> {new_order} for submittal {submittal_id}")
    return True


def check_and_update_submittal(project_id, submittal_id):
    """
    Check if ball_in_court, status, title, and submittal_manager from Procore differ from DB, update if needed.
    
    Args:
        project_id: Procore project ID
        submittal_id: Procore submittal ID
        
    Returns:
        tuple: (ball_updated: bool, status_updated: bool, title_updated: bool, manager_updated: bool, 
                record: ProcoreSubmittal or None, ball_in_court: str or None, status: str or None)
    """
    try:
        result = handle_submittal_update(project_id, submittal_id)
        if result is None:
            logger.warning(f"Failed to parse submittal data for submittal {submittal_id}")
            return False, False, False, False, None, None, None
        
        record, ball_in_court, approvers, status, title, submittal_manager = result
        
        if not record:
            logger.warning(f"No DB record found for submittal {submittal_id}")
            return False, False, False, False, None, ball_in_court, status
        
        ball_updated = False
        status_updated = False
        title_updated = False
        manager_updated = False
        order_bumped = False
        
        # Check and update ball_in_court
        db_ball_value = record.ball_in_court if record.ball_in_court is not None else ""
        webhook_ball_value = ball_in_court if ball_in_court is not None else ""
        
        if db_ball_value != webhook_ball_value:
            logger.info(
                f"Ball in court mismatch detected for submittal {submittal_id}: "
                f"DB='{record.ball_in_court}' vs Procore='{ball_in_court}'"
            )
            
            # Check if new value is multiple assignees (comma-separated)
            is_new_multiple = webhook_ball_value and ',' in webhook_ball_value
            
            # Update the flag: set to True if new value is multiple assignees
            if is_new_multiple:
                record.was_multiple_assignees = True
            elif record.was_multiple_assignees and not is_new_multiple:
                # Was multiple, now single - this is the bounce-back scenario
                if _bump_order_number_to_decimal(record, submittal_id, webhook_ball_value):
                    order_bumped = True
                
                # Reset the flag after handling bounce-back
                record.was_multiple_assignees = False
            
            record.ball_in_court = ball_in_court
            ball_updated = True
        
        # NEW LOGIC: Check if submitter appears as pending in a later workflow group
        # This should trigger a bump regardless of ball_in_court changes
        print(f"[MAIN CHECK] Checking submitter pending workflow condition for submittal {submittal_id}")
        logger.info(f"[MAIN CHECK] Checking submitter pending workflow condition for submittal {submittal_id}")
        
        if approvers:
            print(f"[MAIN CHECK] Approvers list available, calling _check_submitter_pending_in_workflow")
            logger.info(f"[MAIN CHECK] Approvers list available, calling _check_submitter_pending_in_workflow")
            submitter_pending = _check_submitter_pending_in_workflow(approvers)
            print(f"[MAIN CHECK] Result from _check_submitter_pending_in_workflow: {submitter_pending}")
            logger.info(f"[MAIN CHECK] Result from _check_submitter_pending_in_workflow: {submitter_pending}")
        else:
            print(f"[MAIN CHECK] No approvers list available")
            logger.info(f"[MAIN CHECK] No approvers list available")
            submitter_pending = False
        
        if submitter_pending:
            print(f"[MAIN CHECK] ✓ Condition met: Submitter appears as pending approver in workflow for submittal {submittal_id}")
            logger.info(
                f"[MAIN CHECK] ✓ Condition met: Submitter appears as pending approver in workflow for submittal {submittal_id}. "
                f"Checking if order number should be bumped."
            )
            # Only bump if order_number is an integer >= 1 (not already a decimal)
            if record.order_number is not None:
                current_order = record.order_number
                print(f"[MAIN CHECK] Current order number: {current_order}")
                logger.info(f"[MAIN CHECK] Current order number: {current_order}")
                
                is_integer = isinstance(current_order, (int, float)) and current_order >= 1 and current_order == int(current_order)
                print(f"[MAIN CHECK] Order number is integer >= 1: {is_integer}")
                logger.info(f"[MAIN CHECK] Order number is integer >= 1: {is_integer}")
                
                if is_integer:
                    # Use current ball_in_court value (may have been updated above)
                    ball_in_court_for_bump = record.ball_in_court if ball_updated else (ball_in_court or "")
                    print(f"[MAIN CHECK] Calling _bump_order_number_to_decimal with ball_in_court='{ball_in_court_for_bump}'")
                    logger.info(f"[MAIN CHECK] Calling _bump_order_number_to_decimal with ball_in_court='{ball_in_court_for_bump}'")
                    
                    if _bump_order_number_to_decimal(record, submittal_id, ball_in_court_for_bump):
                        order_bumped = True
                        print(f"[MAIN CHECK] ✓ Order number successfully bumped for submittal {submittal_id}")
                        logger.info(
                            f"[MAIN CHECK] ✓ Order number successfully bumped due to submitter pending in workflow for submittal {submittal_id}"
                        )
                else:
                    print(f"[MAIN CHECK] Order number is not an integer >= 1, skipping bump")
                    logger.info(f"[MAIN CHECK] Order number is not an integer >= 1, skipping bump")
            else:
                print(f"[MAIN CHECK] Order number is None, skipping bump")
                logger.info(f"[MAIN CHECK] Order number is None, skipping bump")
        else:
            print(f"[MAIN CHECK] ✗ Condition not met: Submitter does not appear as pending in workflow")
            logger.info(f"[MAIN CHECK] ✗ Condition not met: Submitter does not appear as pending in workflow")
        
        # Check and update status
        db_status_value = record.status if record.status is not None else ""
        webhook_status_value = status if status is not None else ""
        
        if db_status_value != webhook_status_value:
            logger.info(
                f"Status mismatch detected for submittal {submittal_id}: "
                f"DB='{record.status}' vs Procore='{status}'"
            )
            record.status = status
            status_updated = True
        
        # Check and update title
        db_title_value = record.title if record.title is not None else ""
        webhook_title_value = title if title is not None else ""
        
        if db_title_value != webhook_title_value:
            logger.info(
                f"Title mismatch detected for submittal {submittal_id}: "
                f"DB='{record.title}' vs Procore='{title}'"
            )
            record.title = title
            title_updated = True
        
        # Check and update submittal_manager
        db_manager_value = record.submittal_manager if record.submittal_manager is not None else ""
        webhook_manager_value = submittal_manager if submittal_manager is not None else ""
        
        if db_manager_value != webhook_manager_value:
            logger.info(
                f"Submittal manager mismatch detected for submittal {submittal_id}: "
                f"DB='{record.submittal_manager}' vs Procore='{submittal_manager}'"
            )
            record.submittal_manager = submittal_manager
            manager_updated = True
        
        # Update timestamp and commit if any changes
        if ball_updated or status_updated or title_updated or manager_updated or order_bumped:
            record.last_updated = datetime.utcnow()
            db.session.commit()
            
            # Create submittal event for update
            try:
                action = "updated"
                payload = {}
                
                if ball_updated:
                    payload["ball_in_court"] = {
                        "old": db_ball_value,
                        "new": ball_in_court
                    }
                
                if status_updated:
                    payload["status"] = {
                        "old": db_status_value,
                        "new": status
                    }
                
                if title_updated:
                    payload["title"] = {
                        "old": db_title_value,
                        "new": title
                    }
                
                if manager_updated:
                    payload["submittal_manager"] = {
                        "old": db_manager_value,
                        "new": submittal_manager
                    }
                
                if order_bumped:
                    payload["order_bumped"] = True
                    payload["order_number"] = record.order_number
                
                # Only create event if there are actual changes in payload
                if payload:
                    payload_hash = _create_submittal_payload_hash(action, str(submittal_id), payload)
                    
                    # Check if event already exists
                    existing_event = SubmittalEvents.query.filter_by(payload_hash=payload_hash).first()
                    if not existing_event:
                        event = SubmittalEvents(
                            submittal_id=str(submittal_id),
                            action=action,
                            payload=payload,
                            payload_hash=payload_hash,
                            source='Procore'
                        )
                        db.session.add(event)
                        db.session.commit()
                        logger.info(f"Created SubmittalEvent for submittal {submittal_id} update")
                    else:
                        logger.debug(f"SubmittalEvent already exists for submittal {submittal_id} update, skipping")
            except Exception as event_error:
                # Log but don't fail the update if event creation fails
                logger.warning(f"Failed to create SubmittalEvent for submittal {submittal_id} update: {event_error}", exc_info=True)
            
            if ball_updated:
                logger.info(f"Updated ball_in_court for submittal {submittal_id} to '{ball_in_court}'")
            if status_updated:
                logger.info(f"Updated status for submittal {submittal_id} from '{db_status_value}' to '{status}'")
            if title_updated:
                logger.info(f"Updated title for submittal {submittal_id} from '{db_title_value}' to '{title}'")
            if manager_updated:
                logger.info(f"Updated submittal_manager for submittal {submittal_id} from '{db_manager_value}' to '{submittal_manager}'")
            if order_bumped:
                logger.info(f"Order number bumped for submittal {submittal_id}")
        else:
            logger.debug(
                f"All fields match for submittal {submittal_id}: "
                f"ball='{ball_in_court}', status='{status}', title='{title}', manager='{submittal_manager}'"
            )
        
        return ball_updated, status_updated, title_updated, manager_updated, record, ball_in_court, status
            
    except Exception as e:
        logger.error(
            f"Error checking/updating submittal fields for submittal {submittal_id}: {e}",
            exc_info=True
        )
        return False, False, False, False, None, None, None

# Get Viewer URL for Job (without Trello updates)
def get_viewer_url_for_job(job_number, release_number):
    '''
    Function to get procore viewer_url for a job without updating Trello.
    This is used for backfilling viewer_urls into the database.
    
    Args:
        job_number: The job number (integer)
        release_number: The release number (string)
    
    Returns:
        dict with viewer_url if found, None otherwise
        Returns dict with error information if any step fails
    '''
    try:
        # Get companies list
        company_id = get_companies_list()
        if not company_id:
            return {
                "success": False,
                "error": "No Procore company_id returned",
                "job": job_number,
                "release": release_number
            }

        # Get project by company id
        project_id = get_projects_by_company_id(company_id, job_number)
        if not project_id:
            return {
                "success": False,
                "error": f"No Procore project found for job={job_number} company_id={company_id}",
                "job": job_number,
                "release": release_number
            }

        # Get submittals by project id
        identifier = f"{job_number}-{release_number}"
        submittals = get_submittals_by_project_id(project_id, identifier)
        if not submittals:
            return {
                "success": False,
                "error": f"No Procore submittals found for project_id={project_id} identifier={identifier}",
                "job": job_number,
                "release": release_number
            }
        
        final_pdfs = get_final_pdf_viewers(project_id, submittals)
        if not final_pdfs:
            return {
                "success": False,
                "error": f"No final PDF viewers found for project_id={project_id} identifier={identifier}",
                "job": job_number,
                "release": release_number
            }

        # Extract viewer urls from final pdfs
        viewer_url = final_pdfs[0]["viewer_url"]

        return {
            "success": True,
            "viewer_url": viewer_url,
            "job": job_number,
            "release": release_number
        }
    except Exception as e:
        logger.error(
            "Error getting viewer_url for job=%s release=%s: %s",
            job_number,
            release_number,
            str(e),
            exc_info=True
        )
        return {
            "success": False,
            "error": f"Exception: {str(e)}",
            "job": job_number,
            "release": release_number
        }


# Add Procore Link to Trello Card
def add_procore_link_to_trello_card(job, release):
    '''
    Function to add procore drafting document link to related trello card
    '''
    print(job, release)
    job_record = Job.query.filter_by(job=job, release=release).first()
    if not job_record:
        return None
    print(job_record)
    job_number = job_record.job
    release_number = job_record.release
    card_id = job_record.trello_card_id
    if not card_id:
        return None

    # Get companies list
    company_id = get_companies_list()
    print(company_id)
    if not company_id:
        logger.error("No Procore company_id returned; aborting add_procore_link_to_trello_card for job=%s release=%s", job, release)
        return None

    # Get project by company id
    project_id = get_projects_by_company_id(company_id, job_number)
    print(project_id)
    if not project_id:
        logger.error("No Procore project found for job=%s release=%s company_id=%s", job_number, release_number, company_id)
        return None

    # Get submittals by project id
    # job-release
    identifier = f"{job_number}-{release_number}"
    print(identifier)
    submittals = get_submittals_by_project_id(project_id, identifier)
    if not submittals:
        logger.error("No Procore submittals found for project_id=%s identifier=%s", project_id, identifier)
        return None
    final_pdfs = get_final_pdf_viewers(project_id, submittals)
    if not final_pdfs:
        return None

    # Extract viewer urls from final pdfs
    viewer_url = final_pdfs[0]["viewer_url"]

    # Add procore link to trello card
    add_procore_link(card_id, viewer_url)

    # Persist viewer URL on job record
    job_record.viewer_url = viewer_url
    db.session.commit()

    return {
        "card_id": card_id,
        "viewer_url": viewer_url,
    }


def get_drafting_workload():
    '''
    Function to get submittals for drafting workload.
    Returns a list of dicts with submittal_id and project_id for each submittal.
    '''
    # Grab procore instance
    procore = get_procore_client()
    # Collect projects
    projects = procore.get_projects(cfg.PROD_PROCORE_COMPANY_ID)
    
    # Iterate through projects collecting open submittals
    all_submittals = []
    for project in projects:
        if project['id'] == 589044:
            continue
        submittals = procore.get_submittals_for_drafting_workload(project['id'])
        print(f"Submittals: {len(submittals)} for project {project['id']}")
        
        # Extract submittal_id and project_id for each submittal
        for submittal in submittals:
            if isinstance(submittal, dict) and 'id' in submittal:
                all_submittals.append({
                    'submittal_id': str(submittal['id']),
                    'project_id': project['id']
                })

    print(f"Total submittals: {len(all_submittals)}")
    return all_submittals


def cross_reference_db_vs_api():
    """
    Cross-reference database submittals with Procore API response.
    Finds submittals that exist in DB but not in the API response.
    Filters DB submittals to match the same status and type criteria as the API call.
    
    Returns:
        dict with:
            - db_only_submittals: List of ProcoreSubmittal records in DB but not in API
            - api_submittal_ids: Set of submittal IDs from API
            - db_submittal_ids: Set of submittal IDs from DB (filtered)
            - missing_in_api: Count of submittals in DB but not in API
    """
    logger.info("=" * 80)
    logger.info("Starting cross-reference of DB vs API submittals")
    logger.info("=" * 80)
    
    # Get submittals from API
    logger.info("Fetching submittals from Procore API...")
    api_submittals = get_drafting_workload()
    api_submittal_ids = {s['submittal_id'] for s in api_submittals}
    logger.info(f"✓ Found {len(api_submittals)} submittals from API, {len(api_submittal_ids)} unique submittal IDs")
    
    # Debug: Show sample API submittals
    if api_submittals:
        logger.info(f"DEBUG: Sample API submittals (first 5):")
        for i, sub in enumerate(api_submittals[:5]):
            logger.info(f"  [{i+1}] submittal_id={sub.get('submittal_id')} (type={type(sub.get('submittal_id'))}), project_id={sub.get('project_id')}")
        logger.info(f"DEBUG: API submittal_id types: {set(type(sid).__name__ for sid in api_submittal_ids)}")
    
    # Filter DB submittals to match API criteria:
    # - status: "Open" (status_id 203238 in API)
    # - type: "Drafting Release Review" or "Submittal for GC  Approval" or "Submittal for GC Approval"
    valid_types = [
        "Drafting Release Review",
        "Submittal for GC  Approval",
        "Submittal for GC Approval",
        "Submittal for Gc  Approval",
        "Submittal for Gc Approval",
        "Submittal For Gc  Approval",
        "Submittal For Gc Approval",
    ]
    
    logger.info(f"DEBUG: Filtering DB submittals with criteria:")
    logger.info(f"  - status == 'Open'")
    logger.info(f"  - type IN {valid_types}")
    
    # First, check total count in DB
    total_db_count = ProcoreSubmittal.query.count()
    logger.info(f"DEBUG: Total submittals in DB (no filters): {total_db_count}")
    
    # Check count by status
    status_counts = db.session.query(
        ProcoreSubmittal.status,
        db.func.count(ProcoreSubmittal.id)
    ).group_by(ProcoreSubmittal.status).all()
    logger.info(f"DEBUG: DB submittals by status: {dict(status_counts)}")
    
    # Check count by type
    type_counts = db.session.query(
        ProcoreSubmittal.type,
        db.func.count(ProcoreSubmittal.id)
    ).group_by(ProcoreSubmittal.type).all()
    logger.info(f"DEBUG: DB submittals by type (top 10): {dict(type_counts[:10])}")
    
    # Apply filters
    db_submittals = ProcoreSubmittal.query.filter(
        ProcoreSubmittal.status == "Open",
        ProcoreSubmittal.type.in_(valid_types)
    ).all()
    
    logger.info(f"✓ Found {len(db_submittals)} submittals in database matching API criteria")
    
    # Debug: Show sample DB submittals
    if db_submittals:
        logger.info(f"DEBUG: Sample DB submittals (first 5):")
        for i, sub in enumerate(db_submittals[:5]):
            logger.info(f"  [{i+1}] submittal_id={sub.submittal_id} (type={type(sub.submittal_id).__name__}), "
                       f"project_id={sub.procore_project_id}, status={sub.status}, type={sub.type}")
        logger.info(f"DEBUG: DB submittal_id types: {set(type(s.submittal_id).__name__ for s in db_submittals)}")
    
    db_submittal_ids = {s.submittal_id for s in db_submittals}
    logger.info(f"✓ Extracted {len(db_submittal_ids)} unique submittal IDs from filtered DB records")
    
    # Debug: Check for type mismatches
    api_id_types = {type(sid).__name__ for sid in api_submittal_ids}
    db_id_types = {type(sid).__name__ for sid in db_submittal_ids}
    logger.info(f"DEBUG: API submittal_id types: {api_id_types}")
    logger.info(f"DEBUG: DB submittal_id types: {db_id_types}")
    
    if api_id_types != db_id_types:
        logger.warning(f"⚠ Type mismatch detected! API IDs are {api_id_types}, DB IDs are {db_id_types}")
        # Convert both to strings for comparison
        api_submittal_ids_str = {str(sid) for sid in api_submittal_ids}
        db_submittal_ids_str = {str(sid) for sid in db_submittal_ids}
        logger.info(f"DEBUG: Converting both to strings for comparison...")
        logger.info(f"DEBUG: API IDs (as strings): {len(api_submittal_ids_str)}")
        logger.info(f"DEBUG: DB IDs (as strings): {len(db_submittal_ids_str)}")
        
        # Use string comparison
        db_only_ids = db_submittal_ids_str - api_submittal_ids_str
        logger.info(f"DEBUG: Found {len(db_only_ids)} DB-only IDs (using string comparison)")
    else:
        # Direct comparison
        db_only_ids = db_submittal_ids - api_submittal_ids
        logger.info(f"DEBUG: Found {len(db_only_ids)} DB-only IDs (direct comparison)")
    
    # Find submittals in DB but not in API
    # Convert db_submittal_ids to strings if needed for matching
    if api_id_types != db_id_types:
        api_submittal_ids_str = {str(sid) for sid in api_submittal_ids}
        db_only_submittals = [s for s in db_submittals if str(s.submittal_id) in db_only_ids]
    else:
        db_only_submittals = [s for s in db_submittals if s.submittal_id in db_only_ids]
    
    logger.info(f"✓ Found {len(db_only_submittals)} submittals in DB but not in API response")
    
    # Debug: Show sample orphaned submittals
    if db_only_submittals:
        logger.info(f"DEBUG: Sample orphaned submittals (first 5):")
        for i, sub in enumerate(db_only_submittals[:5]):
            logger.info(f"  [{i+1}] submittal_id={sub.submittal_id}, project_id={sub.procore_project_id}, "
                       f"title={sub.title[:50] if sub.title else 'N/A'}..., status={sub.status}, type={sub.type}")
    
    # Group by project_id for easier analysis
    db_only_by_project = {}
    for submittal in db_only_submittals:
        project_id = submittal.procore_project_id
        if project_id not in db_only_by_project:
            db_only_by_project[project_id] = []
        db_only_by_project[project_id].append(submittal)
    
    logger.info(f"✓ DB-only submittals are in {len(db_only_by_project)} unique projects")
    
    # Debug: Show projects with orphaned submittals
    if db_only_by_project:
        logger.info(f"DEBUG: Projects with orphaned submittals:")
        for project_id, submittals in list(db_only_by_project.items())[:10]:
            logger.info(f"  Project {project_id}: {len(submittals)} orphaned submittals")
    
    # Summary
    logger.info("=" * 80)
    logger.info("Cross-reference Summary:")
    logger.info(f"  API submittals: {len(api_submittal_ids)}")
    logger.info(f"  DB submittals (filtered): {len(db_submittal_ids)}")
    logger.info(f"  Orphaned submittals (in DB, not in API): {len(db_only_submittals)}")
    logger.info(f"  Projects with orphaned submittals: {len(db_only_by_project)}")
    logger.info("=" * 80)
    
    return {
        'db_only_submittals': db_only_submittals,
        'db_only_by_project': db_only_by_project,
        'api_submittal_ids': api_submittal_ids,
        'db_submittal_ids': db_submittal_ids,
        'missing_in_api': len(db_only_submittals),
        'api_count': len(api_submittal_ids),
        'db_count': len(db_submittal_ids)
    }


def check_webhook_health(project_ids=None):
    """
    Check webhook health for specified projects or all projects with submittals in DB.
    
    Args:
        project_ids: Optional list of project IDs to check. If None, checks all projects
                     that have submittals in the database.
    
    Returns:
        dict with:
            - projects_with_webhooks: List of project IDs that have webhooks
            - projects_without_webhooks: List of project IDs missing webhooks
            - webhook_details: Dict mapping project_id to webhook info
            - broken_webhooks: List of projects with webhooks that appear broken
    """
    logger.info("Starting webhook health check")
    procore = get_procore_client()
    
    # If no project_ids provided, get all unique project IDs from DB
    # Filter to match the same criteria as the API call (status=Open, valid types)
    if project_ids is None:
        valid_types = [
            "Drafting Release Review",
            "Submittal for GC  Approval",
            "Submittal for GC Approval"
        ]
        db_projects = db.session.query(ProcoreSubmittal.procore_project_id).filter(
            ProcoreSubmittal.status == "Open",
            ProcoreSubmittal.type.in_(valid_types)
        ).distinct().all()
        project_ids = [str(p[0]) for p in db_projects if p[0]]
        logger.info(f"Checking webhooks for {len(project_ids)} projects from database (filtered by status=Open, valid types)")
    else:
        # Convert to strings for consistency
        project_ids = [str(pid) for pid in project_ids]
        logger.info(f"Checking webhooks for {len(project_ids)} specified projects")
    
    projects_with_webhooks = []
    projects_without_webhooks = []
    webhook_details = {}
    broken_webhooks = []
    
    for project_id in project_ids:
        try:
            # List webhooks for this project
            webhooks = procore.list_project_webhooks(int(project_id), 'mile-high-metal-works')
            
            if not webhooks or len(webhooks) == 0:
                projects_without_webhooks.append(project_id)
                webhook_details[project_id] = {
                    'has_webhook': False,
                    'webhook_count': 0,
                    'webhooks': []
                }
                logger.warning(f"Project {project_id} has no webhooks")
            else:
                projects_with_webhooks.append(project_id)
                
                # Check webhook details and triggers
                webhook_info = []
                for webhook in webhooks:
                    hook_id = webhook.get('id')
                    if hook_id:
                        try:
                            # Get webhook details
                            details = procore.get_webhook_details(int(project_id), hook_id)
                            triggers = procore.get_webhook_triggers(int(project_id), hook_id)
                            
                            # Check if webhook has the required triggers (create and update for Submittals)
                            has_create = any(
                                t.get('resource_name') == 'Submittals' and 
                                t.get('event_type') == 'create'
                                for t in triggers
                            )
                            has_update = any(
                                t.get('resource_name') == 'Submittals' and 
                                t.get('event_type') == 'update'
                                for t in triggers
                            )
                            
                            webhook_info.append({
                                'id': hook_id,
                                'destination_url': details.get('destination_url'),
                                'namespace': details.get('namespace'),
                                'has_create_trigger': has_create,
                                'has_update_trigger': has_update,
                                'triggers': triggers,
                                'is_healthy': has_create and has_update
                            })
                            
                            # Mark as broken if missing required triggers
                            if not (has_create and has_update):
                                if project_id not in broken_webhooks:
                                    broken_webhooks.append(project_id)
                        except Exception as e:
                            logger.error(f"Error checking webhook {hook_id} for project {project_id}: {e}")
                            webhook_info.append({
                                'id': hook_id,
                                'error': str(e)
                            })
                
                webhook_details[project_id] = {
                    'has_webhook': True,
                    'webhook_count': len(webhooks),
                    'webhooks': webhook_info
                }
                
        except Exception as e:
            logger.error(f"Error checking webhooks for project {project_id}: {e}")
            projects_without_webhooks.append(project_id)
            webhook_details[project_id] = {
                'has_webhook': False,
                'error': str(e)
            }
    
    logger.info(f"Webhook health check complete: {len(projects_with_webhooks)} with webhooks, "
                f"{len(projects_without_webhooks)} without, {len(broken_webhooks)} broken")
    
    return {
        'projects_with_webhooks': projects_with_webhooks,
        'projects_without_webhooks': projects_without_webhooks,
        'broken_webhooks': broken_webhooks,
        'webhook_details': webhook_details,
        'total_checked': len(project_ids)
    }


def check_orphaned_submittals_webhooks():
    """
    Check webhook health for projects that have submittals in DB but not in API response.
    This helps identify if missing webhooks are causing submittals to not appear in API.
    
    Returns:
        dict combining cross-reference and webhook health check results
    """
    logger.info("Starting orphaned submittals webhook check")
    
    # First, cross-reference DB vs API
    cross_ref = cross_reference_db_vs_api()
    
    # Get unique project IDs from DB-only submittals
    orphaned_project_ids = list(cross_ref['db_only_by_project'].keys())
    
    if not orphaned_project_ids:
        logger.info("No orphaned submittals found - all DB submittals are in API response")
        return {
            'cross_reference': cross_ref,
            'webhook_check': None,
            'summary': 'No orphaned submittals to check'
        }
    
    logger.info(f"Checking webhooks for {len(orphaned_project_ids)} projects with orphaned submittals")
    
    # Check webhooks for these projects
    webhook_check = check_webhook_health(orphaned_project_ids)
    
    # Combine results
    result = {
        'cross_reference': cross_ref,
        'webhook_check': webhook_check,
        'summary': {
            'orphaned_submittals_count': cross_ref['missing_in_api'],
            'orphaned_projects_count': len(orphaned_project_ids),
            'orphaned_projects_without_webhooks': len([
                pid for pid in orphaned_project_ids 
                if pid in webhook_check['projects_without_webhooks']
            ]),
            'orphaned_projects_with_broken_webhooks': len([
                pid for pid in orphaned_project_ids 
                if pid in webhook_check['broken_webhooks']
            ])
        }
    }
    
    logger.info(f"Orphaned submittals check complete: {result['summary']}")
    return result


def check_all_relevant_projects_webhooks():
    """
    Check webhook health for all projects that have submittals in the API response.
    This ensures all 37 relevant projects have proper webhooks configured.
    
    Returns:
        dict with webhook health check results for all relevant projects
    """
    logger.info("Starting webhook health check for all relevant projects")
    
    # Get submittals from API to identify relevant projects
    api_submittals = get_drafting_workload()
    
    # Get unique project IDs from API response
    relevant_project_ids = list(set(s['project_id'] for s in api_submittals))
    logger.info(f"Found {len(relevant_project_ids)} relevant projects with submittals in API")
    
    # Check webhooks for all relevant projects
    webhook_check = check_webhook_health(relevant_project_ids)
    
    # Add summary
    webhook_check['summary'] = {
        'total_relevant_projects': len(relevant_project_ids),
        'projects_with_webhooks': len(webhook_check['projects_with_webhooks']),
        'projects_without_webhooks': len(webhook_check['projects_without_webhooks']),
        'projects_with_broken_webhooks': len(webhook_check['broken_webhooks']),
        'coverage_percentage': round(
            (len(webhook_check['projects_with_webhooks']) / len(relevant_project_ids) * 100) 
            if relevant_project_ids else 0, 
            2
        )
    }
    
    logger.info(f"Relevant projects webhook check complete: {webhook_check['summary']}")
    return webhook_check


def comprehensive_health_scan(skip_user_prompt=False):
    """
    Comprehensive health scan for orphaned submittals:
    1. Find submittals in DB but not in API response
    2. Check webhooks for projects with orphaned submittals
    3. Fetch full submittal data from API for each orphaned submittal
    4. Compare ball_in_court and status between DB and API
    5. List all differences and provide recommendations
    
    Args:
        skip_user_prompt: If True, skip the interactive user prompt for updating records.
                          Use this when calling from API endpoints.
    
    Returns:
        dict with:
            - orphaned_submittals: List of orphaned submittal analysis
            - webhook_status: Webhook health for orphaned projects
            - summary: Summary statistics and recommendations
            - differences: Detailed list of all mismatches
            - updated_count: Number of records updated (if user confirmed)
    """
    logger.info("=" * 80)
    logger.info("Starting Comprehensive Health Scan")
    logger.info("=" * 80)
    
    # Step 1: Find orphaned submittals
    logger.info("Step 1: Finding orphaned submittals (in DB but not in API response)...")
    cross_ref = cross_reference_db_vs_api()
    orphaned_submittals = cross_ref['db_only_submittals']
    orphaned_by_project = cross_ref['db_only_by_project']
    
    if not orphaned_submittals:
        logger.info("✓ No orphaned submittals found - all DB submittals are in API response")
        return {
            'orphaned_submittals': [],
            'webhook_status': None,
            'summary': {
                'total_orphaned': 0,
                'projects_with_orphans': 0,
                'sync_issues': 0,
                'deleted_submittals': 0,
                'api_fetch_errors': 0,
                'webhook_issues': 0,
                'projects_missing_webhooks': 0
            },
            'differences': {
                'sync_issues': [],
                'deleted_submittals': [],
                'api_fetch_errors': []
            },
            'updated_count': 0
        }
    
    logger.info(f"✓ Found {len(orphaned_submittals)} orphaned submittals in {len(orphaned_by_project)} projects")
    
    # Step 2: Check webhooks for projects with orphaned submittals
    logger.info("Step 2: Checking webhooks for projects with orphaned submittals...")
    orphaned_project_ids = list(orphaned_by_project.keys())
    webhook_status = check_webhook_health(orphaned_project_ids)
    logger.info(f"✓ Webhook check complete: {len(webhook_status['projects_without_webhooks'])} projects missing webhooks")
    
    # Step 3 & 4: Fetch API data and compare for each orphaned submittal
    logger.info("Step 3: Fetching full submittal data from API and comparing with DB...")
    procore = get_procore_client()
    differences = []
    sync_issues = []
    deleted_submittals = []
    api_fetch_errors = []
    
    for submittal in orphaned_submittals:
        submittal_id = submittal.submittal_id
        project_id = submittal.procore_project_id
        
        try:
            # Fetch full submittal data from API
            api_submittal_data = get_submittal_by_id(int(project_id), int(submittal_id))
            
            if not api_submittal_data or not isinstance(api_submittal_data, dict):
                # Submittal doesn't exist in API - likely deleted/archived
                deleted_submittals.append({
                    'submittal_id': submittal_id,
                    'project_id': project_id,
                    'project_name': submittal.project_name,
                    'title': submittal.title,
                    'db_status': submittal.status,
                    'db_ball_in_court': submittal.ball_in_court,
                    'recommendation': 'Consider removing from DB or marking as archived'
                })
                logger.warning(f"  Submittal {submittal_id} (project {project_id}) not found in API - likely deleted")
                continue
            
            # Parse ball_in_court from API data
            parsed = parse_ball_in_court_from_submittal(api_submittal_data)
            api_ball_in_court = parsed.get("ball_in_court") if parsed else None
            
            # Extract status from API data
            status_obj = api_submittal_data.get("status")
            if isinstance(status_obj, dict):
                api_status = status_obj.get("name")
            elif isinstance(status_obj, str):
                api_status = status_obj
            else:
                api_status = None
            api_status = str(api_status).strip() if api_status else None
            
            # Compare with DB
            db_ball_in_court = submittal.ball_in_court if submittal.ball_in_court else None
            db_status = submittal.status if submittal.status else None
            
            ball_mismatch = str(db_ball_in_court or "") != str(api_ball_in_court or "")
            status_mismatch = str(db_status or "") != str(api_status or "")
            
            if ball_mismatch or status_mismatch:
                # Sync issue - submittal exists in API but values don't match
                diff = {
                    'submittal_id': submittal_id,
                    'project_id': project_id,
                    'project_name': submittal.project_name,
                    'title': submittal.title,
                    'ball_in_court': {
                        'db': db_ball_in_court,
                        'api': api_ball_in_court,
                        'mismatch': ball_mismatch
                    },
                    'status': {
                        'db': db_status,
                        'api': api_status,
                        'mismatch': status_mismatch
                    },
                    'recommendation': 'Sync issue - DB values are out of date. Webhook may not be working or submittal was updated outside of webhook flow.'
                }
                differences.append(diff)
                sync_issues.append(diff)
                logger.warning(f"  ⚠ Sync issue for submittal {submittal_id}: ball_in_court mismatch={ball_mismatch}, status mismatch={status_mismatch}")
            else:
                # Values match - submittal exists in API but wasn't in the filtered API response
                # This could mean status/type changed, or it's filtered out for another reason
                logger.info(f"  ✓ Submittal {submittal_id} exists in API with matching values (not in filtered response)")
                
        except Exception as e:
            # Error fetching from API
            api_fetch_errors.append({
                'submittal_id': submittal_id,
                'project_id': project_id,
                'project_name': submittal.project_name,
                'title': submittal.title,
                'error': str(e),
                'recommendation': 'Check API access and submittal permissions'
            })
            logger.error(f"  ✗ Error fetching submittal {submittal_id} from API: {e}")
    
    logger.info(f"✓ Comparison complete:")
    logger.info(f"  - Sync issues (mismatches): {len(sync_issues)}")
    logger.info(f"  - Deleted submittals (not in API): {len(deleted_submittals)}")
    logger.info(f"  - API fetch errors: {len(api_fetch_errors)}")
    
    # Compile results
    summary = {
        'total_orphaned': len(orphaned_submittals),
        'projects_with_orphans': len(orphaned_by_project),
        'sync_issues': len(sync_issues),
        'deleted_submittals': len(deleted_submittals),
        'api_fetch_errors': len(api_fetch_errors),
        'webhook_issues': len(webhook_status['projects_without_webhooks']),
        'projects_missing_webhooks': len(webhook_status['projects_without_webhooks'])
    }
    
    # Log detailed differences
    logger.info("=" * 80)
    logger.info("Detailed Differences:")
    logger.info("=" * 80)
    
    if sync_issues:
        logger.info(f"\n🔴 SYNC ISSUES ({len(sync_issues)} submittals with mismatches):")
        for issue in sync_issues:
            logger.info(f"  Submittal {issue['submittal_id']} (Project {issue['project_id']} - {issue['project_name']})")
            logger.info(f"    Title: {issue['title']}")
            if issue['ball_in_court']['mismatch']:
                logger.info(f"    ⚠ ball_in_court: DB='{issue['ball_in_court']['db']}' vs API='{issue['ball_in_court']['api']}'")
            if issue['status']['mismatch']:
                logger.info(f"    ⚠ status: DB='{issue['status']['db']}' vs API='{issue['status']['api']}'")
            logger.info(f"    Recommendation: {issue['recommendation']}")
            logger.info("")
    
    if deleted_submittals:
        logger.info(f"\n🟡 DELETED/ARCHIVED SUBMITTALS ({len(deleted_submittals)} submittals not found in API):")
        for deleted in deleted_submittals:
            logger.info(f"  Submittal {deleted['submittal_id']} (Project {deleted['project_id']} - {deleted['project_name']})")
            logger.info(f"    Title: {deleted['title']}")
            logger.info(f"    Last known status: {deleted['db_status']}, ball_in_court: {deleted['db_ball_in_court']}")
            logger.info(f"    Recommendation: {deleted['recommendation']}")
            logger.info("")
    
    if api_fetch_errors:
        logger.info(f"\n🔴 API FETCH ERRORS ({len(api_fetch_errors)} submittals):")
        for error in api_fetch_errors:
            logger.info(f"  Submittal {error['submittal_id']} (Project {error['project_id']} - {error['project_name']})")
            logger.info(f"    Title: {error['title']}")
            logger.info(f"    Error: {error['error']}")
            logger.info(f"    Recommendation: {error['recommendation']}")
            logger.info("")
    
    if webhook_status['projects_without_webhooks']:
        logger.info(f"\n🔴 PROJECTS MISSING WEBHOOKS ({len(webhook_status['projects_without_webhooks'])} projects):")
        for project_id in webhook_status['projects_without_webhooks']:
            logger.info(f"  Project {project_id}: No webhooks configured")
        logger.info("")
    
    logger.info("=" * 80)
    logger.info("Health Scan Summary:")
    logger.info(f"  Total orphaned submittals: {summary['total_orphaned']}")
    logger.info(f"  Projects with orphans: {summary['projects_with_orphans']}")
    logger.info(f"  Sync issues (mismatches): {summary['sync_issues']}")
    logger.info(f"  Deleted/archived submittals: {summary['deleted_submittals']}")
    logger.info(f"  API fetch errors: {summary['api_fetch_errors']}")
    logger.info(f"  Projects missing webhooks: {summary['projects_missing_webhooks']}")
    logger.info("=" * 80)
    
    # Ask user if they want to update DB records to match API (only if not skipping prompt)
    updated_count = 0
    if sync_issues and not skip_user_prompt:
        print("\n" + "=" * 80)
        print(f"Found {len(sync_issues)} submittals with sync issues (DB values don't match API)")
        print("=" * 80)
        user_input = input("\nWould you like to update DB records to match API values? (yes/no): ").strip().lower()
        
        if user_input == 'yes':
            logger.info("User confirmed: Updating DB records to match API values...")
            for issue in sync_issues:
                try:
                    # Find the DB record
                    db_record = ProcoreSubmittal.query.filter_by(submittal_id=issue['submittal_id']).first()
                    if not db_record:
                        logger.warning(f"  Could not find DB record for submittal {issue['submittal_id']}")
                        continue
                    
                    # Update ball_in_court if there's a mismatch
                    if issue['ball_in_court']['mismatch']:
                        old_value = db_record.ball_in_court
                        db_record.ball_in_court = issue['ball_in_court']['api']
                        logger.info(f"  Updated submittal {issue['submittal_id']}: ball_in_court '{old_value}' -> '{issue['ball_in_court']['api']}'")
                    
                    # Update status if there's a mismatch
                    if issue['status']['mismatch']:
                        old_value = db_record.status
                        db_record.status = issue['status']['api']
                        logger.info(f"  Updated submittal {issue['submittal_id']}: status '{old_value}' -> '{issue['status']['api']}'")
                    
                    # Update last_updated timestamp
                    db_record.last_updated = datetime.utcnow()
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"  Error updating submittal {issue['submittal_id']}: {e}")
            
            # Commit all changes
            try:
                db.session.commit()
                logger.info(f"✓ Successfully updated {updated_count} submittal records in database")
                print(f"\n✓ Successfully updated {updated_count} submittal records in database")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error committing updates to database: {e}")
                print(f"\n✗ Error committing updates to database: {e}")
        else:
            logger.info("User declined to update DB records")
            print("\nSkipping DB updates.")
    
    return {
        'orphaned_submittals': orphaned_submittals,
        'webhook_status': webhook_status,
        'summary': summary,
        'differences': {
            'sync_issues': sync_issues,
            'deleted_submittals': deleted_submittals,
            'api_fetch_errors': api_fetch_errors
        },
        'updated_count': updated_count
    }


if __name__ == "__main__":
    from app import create_app
    app = create_app()
    # app context
    with app.app_context():

        # # Check for orphaned submittals and their webhook status
        # result = check_orphaned_submittals_webhooks()
        # print(f"Found {result['summary']['orphaned_submittals_count']} orphaned submittals")
        # print(f"In {result['summary']['orphaned_projects_count']} projects")
        # print(f"{result['summary']['orphaned_projects_without_webhooks']} projects missing webhooks")

        # # Or check all relevant projects
        # webhook_status = check_all_relevant_projects_webhooks()
        # print(f"Webhook coverage: {webhook_status['summary']['coverage_percentage']}%")
        # Comprehensive health scan
        result = comprehensive_health_scan()
        print(f"Total orphaned submittals: {result['summary']['total_orphaned']}")
        print(f"Projects with orphans: {result['summary']['projects_with_orphans']}")
        print(f"Sync issues (mismatches): {result['summary']['sync_issues']}")
        print(f"Deleted/archived submittals: {result['summary']['deleted_submittals']}")
        print(f"API fetch errors: {result['summary']['api_fetch_errors']}")
        print(f"Projects missing webhooks: {result['summary']['projects_missing_webhooks']}")
        if 'updated_count' in result:
            print(f"Updated records: {result['updated_count']}")
