import requests
from app.config import Config as cfg
from app.models import db, Job
from app.trello.api import add_procore_link
from app import create_app
from app.procore.procore_auth import get_access_token

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
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
    }
    response = requests.get(url, headers=headers)
    companies = response.json()
    company_id = companies[0]["id"]
    return company_id


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
    response = requests.get(url, headers=headers)
    projects = response.json()
    for project in projects:
        if project["project_number"] == str(project_number):
            return project["id"]
    return None

# Get Submittals by Project ID and Identifier
def get_submittals_by_project_id(project_id, identifier):
    """Get submittals by project ID and identifier"""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    response = requests.get(url, headers=headers)
    submittals = response.json()
    return [
        s for s in submittals
        if identifier.lower() in s.get("title", "").lower()
        and s.get("type", {}).get("name") == "For Construction"
    ]


# Get Workflow Data by Project ID and Submittal ID
def get_workflow_data(project_id, submittal_id):
    """Fetch workflow data for a given submittal"""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/workflow_data"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    response = requests.get(url, headers=headers)
    return response.json()


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
        for att in workflow_data.get("attachments", []):
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

    # Get project by company id
    project_id = get_projects_by_company_id(company_id, job_number)
    print(project_id)

    # Get submittals by project id
    # job-release
    identifier = f"{job_number}-{release_number}"
    print(identifier)
    submittals = get_submittals_by_project_id(project_id, identifier)
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

# if __name__ == "__main__":
#     # refresh_access_token()
#     app = create_app()
#     # app context
#     with app.app_context():

#         add_procore_link_to_trello_card(200, '436')
#         print("Procore link added to trello card")
