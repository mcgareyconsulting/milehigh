import requests
from app.config import Config as cfg

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

def refresh_access_token():
    url = "https://login.procore.com/oauth/token/"
    body = {
        "grant_type": "refresh_token",
        "refresh_token": cfg.PROD_PROCORE_REFRESH_TOKEN,
        "client_id": cfg.PROD_PROCORE_CLIENT_ID,
        "client_secret": cfg.PROD_PROCORE_CLIENT_SECRET,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    }
    response = requests.post(url, data=body)
    print(response.json())
    return response.json()

# TEST Get Companies List
def get_companies_list():
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.0/companies"
    headers = {
        "Authorization": f"Bearer {cfg.PROD_PROCORE_ACCESS_TOKEN}",
    }
    response = requests.get(url, headers=headers)
    company_id = response.json()[0]["id"]
    return company_id


# TEST Get Projects by Company ID
def get_projects_by_company_id(company_id):
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects?company_id={company_id}"
    headers = {
        "Authorization": f"Bearer {cfg.PROD_PROCORE_ACCESS_TOKEN}",
        "Procore-Company-Id": str(company_id),
    }
    response = requests.get(url, headers=headers)
    project_id = response.json()[0]["id"]
    return project_id

# TEST Get Submittals by Project ID
def get_submittals_by_project_id(project_id):
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals/attachments_with_markup"
    headers = {
        "Authorization": f"Bearer {cfg.PROD_PROCORE_ACCESS_TOKEN}",
    }
    body = {
        "project_id": project_id,
    }
    response = requests.get(url, headers=headers, json=body)
    return response.json()


if __name__ == "__main__":
    # refresh_access_token()
    company_id = get_companies_list()
    project_id = get_projects_by_company_id(company_id)
    submittals = get_submittals_by_project_id(project_id)
    print(submittals)
