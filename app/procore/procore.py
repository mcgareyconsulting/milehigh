import logging
import re
import json
import os
import requests
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from requests.exceptions import ConnectionError, Timeout
from urllib3.exceptions import ProtocolError
from app.config import Config as cfg
from app.models import db, Job, ProcoreSubmittal
from app.trello.api import add_procore_link
from app.procore.procore_auth import get_access_token
from app.procore.client import get_procore_client
from app.procore.helpers import parse_ball_in_court_from_submittal


logger = logging.getLogger(__name__)


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
    Compare ball_in_court and status from submittal webhook data against DB record.
    
    Args:
        project_id: The Procore project ID
        submittal_id: The submittal ID (resource_id from webhook)
        
    Returns:
        tuple: (procore_submittal, ball_in_court, approvers, status) or None if parsing fails
        - procore_submittal: ProcoreSubmittal DB record or None if not found
        - ball_in_court: str or None - User who has the ball in court
        - approvers: list - List of approver data
        - status: str or None - Status of the submittal from Procore
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
    
    # Look up the DB record
    procore_submittal = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
    
    # Always return a tuple, even if procore_submittal is None
    return procore_submittal, ball_in_court, approvers, status


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
            submittal_drafting_status='STARTED',  # Default value
            created_at=datetime.utcnow(),
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
    in a later workflow group (non-zero workflow_group_number).
    
    Args:
        approvers: List of approver dictionaries from submittal data
        
    Returns:
        bool: True if submitter appears as pending in a later workflow group
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
    
    # Check if submitter appears in any non-zero workflow group with "Pending" response
    print(f"[SUBMITTER CHECK] Checking if submitter appears as pending in later workflow groups...")
    logger.info(f"[SUBMITTER CHECK] Checking if submitter appears as pending in later workflow groups...")
    
    for approver in approvers:
        if not isinstance(approver, dict):
            continue
        
        workflow_group = approver.get("workflow_group_number")
        if workflow_group is None or workflow_group == 0:
            continue  # Skip submitter or approvers without workflow_group_number
        
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
        
        if name_match:
            print(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('name')}' appears as pending at workflow_group_number={workflow_group}")
            logger.info(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('name')}' appears as pending at workflow_group_number={workflow_group}")
            return True
        if login_match:
            print(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('login')}' appears as pending at workflow_group_number={workflow_group}")
            logger.info(f"[SUBMITTER CHECK] ✓ MATCH FOUND: Submitter '{submitter.get('login')}' appears as pending at workflow_group_number={workflow_group}")
            return True
    
    print(f"[SUBMITTER CHECK] ✗ No match found: Submitter does not appear as pending in later workflow groups")
    logger.info(f"[SUBMITTER CHECK] ✗ No match found: Submitter does not appear as pending in later workflow groups")
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
    Check if ball_in_court and status from Procore differ from DB, update if needed.
    
    Args:
        project_id: Procore project ID
        submittal_id: Procore submittal ID
        
    Returns:
        tuple: (ball_updated: bool, status_updated: bool, record: ProcoreSubmittal or None, 
                ball_in_court: str or None, status: str or None)
    """
    try:
        result = handle_submittal_update(project_id, submittal_id)
        if result is None:
            logger.warning(f"Failed to parse submittal data for submittal {submittal_id}")
            return False, False, None, None, None
        
        record, ball_in_court, approvers, status = result
        
        if not record:
            logger.warning(f"No DB record found for submittal {submittal_id}")
            return False, False, None, ball_in_court, status
        
        ball_updated = False
        status_updated = False
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
        
        # Update timestamp and commit if any changes
        if ball_updated or status_updated or order_bumped:
            record.last_updated = datetime.utcnow()
            db.session.commit()
            
            if ball_updated:
                logger.info(f"Updated ball_in_court for submittal {submittal_id} to '{ball_in_court}'")
            if status_updated:
                logger.info(f"Updated status for submittal {submittal_id} from '{db_status_value}' to '{status}'")
            if order_bumped:
                logger.info(f"Order number bumped for submittal {submittal_id}")
        else:
            logger.debug(
                f"Ball in court and status match for submittal {submittal_id}: "
                f"ball='{ball_in_court}', status='{status}'"
            )
        
        return ball_updated, status_updated, record, ball_in_court, status
            
    except Exception as e:
        logger.error(
            f"Error checking/updating ball_in_court and status for submittal {submittal_id}: {e}",
            exc_info=True
        )
        return False, False, None, None, None
        
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
        
        # Update timestamp and commit if any changes
        if ball_updated or status_updated:
            record.last_updated = datetime.utcnow()
            db.session.commit()
            
            if ball_updated:
                logger.info(f"Updated ball_in_court for submittal {submittal_id} to '{ball_in_court}'")
            if status_updated:
                logger.info(f"Updated status for submittal {submittal_id} from '{db_status_value}' to '{status}'")
        else:
            logger.debug(
                f"Ball in court and status match for submittal {submittal_id}: "
                f"ball='{ball_in_court}', status='{status}'"
            )
        
        return ball_updated, status_updated, record, ball_in_court, status
            
    except Exception as e:
        logger.error(
            f"Error checking/updating ball_in_court and status for submittal {submittal_id}: {e}",
            exc_info=True
        )
        return False, False, None, None, None

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

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    # app context
    with app.app_context():

        procore = get_procore_client()
        proj = 3203976
        sub = 64744482
        result = handle_submittal_update(proj, sub)
        if result is None:
            print("Failed to parse submittal data")
        else:
            procore_submittal, ball_in_court, approvers, status = result
            print(f"DB Record: {procore_submittal}")
            print(f"Ball in Court: {ball_in_court}")
            print(f"Status: {status}")
            print(f"Approvers: {len(approvers) if approvers else 0} approvers")
            if procore_submittal:
                print(f"DB ball_in_court: {procore_submittal.ball_in_court}")
                print(f"DB status: {procore_submittal.status}")
                print(f"Ball in court match: {procore_submittal.ball_in_court == ball_in_court}")
                print(f"Status match: {procore_submittal.status == status}")
