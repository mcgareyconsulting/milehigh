import logging
import re
import requests
from datetime import datetime
from sqlalchemy.exc import IntegrityError
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
        
    except Exception as e:
        error_msg = f"Exception in create_submittal_from_webhook: {str(e)}"
        logger.error(
            f"Error creating submittal {submittal_id} from webhook: {e}",
            exc_info=True
        )
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(f"Error during rollback: {rollback_error}", exc_info=True)
        return False, None, error_msg


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
                # Convert integer order numbers to urgent decimals
                if record.order_number is not None:
                    current_order = record.order_number
                    # Check if order_number is an integer >= 1
                    if isinstance(current_order, (int, float)) and current_order >= 1 and current_order == int(current_order):
                        # Convert to urgent decimal (e.g., 6 -> 0.6)
                        target_decimal = current_order / 10.0
                        
                        # Find all existing order numbers for this ball_in_court that are < 1
                        existing_urgent_orders = db.session.query(ProcoreSubmittal.order_number).filter(
                            ProcoreSubmittal.ball_in_court == webhook_ball_value,
                            ProcoreSubmittal.submittal_id != submittal_id,  # Exclude current submittal
                            ProcoreSubmittal.order_number < 1,
                            ProcoreSubmittal.order_number.isnot(None)
                        ).all()
                        existing_urgent_orders = [float(o[0]) for o in existing_urgent_orders if o[0] is not None]
                        
                        # Find next available decimal that is more urgent (smaller) than any collision
                        new_order = target_decimal
                        if target_decimal in existing_urgent_orders:
                            # Collision detected - find next available smaller decimal
                            if existing_urgent_orders:
                                smallest_existing = min(existing_urgent_orders)
                                candidate = smallest_existing / 2.0
                                
                                # Keep halving until we find a value that's not in the list
                                max_iterations = 10  # Prevent infinite loops
                                iteration = 0
                                while candidate in existing_urgent_orders and candidate > 0.001 and iteration < max_iterations:
                                    candidate = candidate / 2.0
                                    iteration += 1
                                
                                # If we still have a collision after iterations, use a fixed small value
                                if candidate in existing_urgent_orders or candidate <= 0:
                                    candidate = 0.01
                                
                                new_order = candidate
                            else:
                                # No existing urgent orders, but target_decimal is somehow in the list (shouldn't happen)
                                new_order = target_decimal / 2.0
                        
                        record.order_number = new_order
                        logger.info(
                            f"Bounce-back detected: Converted order_number from {int(current_order)} to {new_order} "
                            f"for submittal {submittal_id} (was_multiple_assignees={record.was_multiple_assignees})"
                        )
                
                # Reset the flag after handling bounce-back
                record.was_multiple_assignees = False
            
            record.ball_in_court = ball_in_court
            ball_updated = True
        
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
