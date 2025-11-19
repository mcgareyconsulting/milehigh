import logging
import re
import requests
from datetime import datetime
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
    Compare ball_in_court from submittal webhook data against DB record.
    
    Args:
        submittal_id: The submittal ID (resource_id from webhook)
        submittal: Dict containing submittal data from Procore webhook
        
    Returns:
        tuple: (procore_submittal, ball_in_court, approvers) or None if parsing fails
        - procore_submittal: ProcoreSubmittal DB record or None if not found
        - ball_in_court: str or None - User who has the ball in court
        - approvers: list - List of approver data
    """
    # Collect submittal data and pass to parser function
    submittal = get_submittal_by_id(project_id, submittal_id)
    parsed = parse_ball_in_court_from_submittal(submittal)
    if parsed is None:
        return None
    
    ball_in_court = parsed.get("ball_in_court")
    approvers = parsed.get("approvers", [])
    
    # Look up the DB record
    procore_submittal = ProcoreSubmittal.query.filter_by(submittal_id=str(submittal_id)).first()
    
    # Always return a tuple, even if procore_submittal is None
    return procore_submittal, ball_in_court, approvers


def check_and_update_ball_in_court(project_id, submittal_id, socketio_instance=None):
    """
    Check if ball_in_court from Procore differs from DB, update if needed, and emit websocket event.
    
    Args:
        project_id: Procore project ID
        submittal_id: Procore submittal ID
        socketio_instance: Optional SocketIO instance to emit events
        
    Returns:
        tuple: (updated: bool, record: ProcoreSubmittal or None, ball_in_court: str or None)
    """
    try:
        record, ball_in_court, approvers = handle_submittal_update(project_id, submittal_id)
        
        if not record:
            logger.warning(f"No DB record found for submittal {submittal_id}")
            return False, None, ball_in_court
        
        # Normalize None to empty string for comparison
        db_value = record.ball_in_court if record.ball_in_court is not None else ""
        webhook_value = ball_in_court if ball_in_court is not None else ""
        
        # Check for mismatch
        if db_value != webhook_value:
            logger.info(
                f"Ball in court mismatch detected for submittal {submittal_id}: "
                f"DB='{record.ball_in_court}' vs Webhook='{ball_in_court}'"
            )
            
            # Update database
            record.ball_in_court = ball_in_court
            record.last_updated = datetime.utcnow()
            db.session.commit()
            
            logger.info(
                f"Updated ball_in_court for submittal {submittal_id} to '{ball_in_court}'"
            )
            
            # Emit websocket event if socketio instance provided
            if socketio_instance:
                socketio_instance.emit('ball_in_court_updated', {
                    'submittal_id': str(submittal_id),
                    'ball_in_court': ball_in_court,
                    'timestamp': datetime.utcnow().isoformat()
                })
                logger.info(f"Emitted websocket event for submittal {submittal_id}")
            
            return True, record, ball_in_court
        else:
            logger.debug(
                f"Ball in court match for submittal {submittal_id}: '{ball_in_court}'"
            )
            return False, record, ball_in_court
            
    except Exception as e:
        logger.error(
            f"Error checking/updating ball_in_court for submittal {submittal_id}: {e}",
            exc_info=True
        )
        return False, None, None

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
            procore_submittal, ball_in_court, approvers = result
            print(f"DB Record: {procore_submittal}")
            print(f"Ball in Court: {ball_in_court}")
            print(f"Approvers: {len(approvers) if approvers else 0} approvers")
            if procore_submittal:
                print(f"DB ball_in_court: {procore_submittal.ball_in_court}")
                print(f"Match: {procore_submittal.ball_in_court == ball_in_court}")
