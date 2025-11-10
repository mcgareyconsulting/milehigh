import requests
from app.procore.procore_auth import refresh_tokens, get_access_token
from app.models import ProcoreToken
from typing import Optional, Dict, List
from app.config import Config as cfg

class ProcoreAPI:
    """ProcoreAPI connection layer utilizing requests session for better performance and error handling."""
    BASE_URL = "https://api.procore.com"

    def __init__(self, client_id, client_secret, webhook_url):
        self.client_id = client_id
        self.client_secret = client_secret
        self.webhook_url = webhook_url
        self.session = requests.Session()
        
        if not all([self.client_id, self.client_secret, self.webhook_url]):
            raise ValueError("Missing Procore configuration")

        # Reusable HTTP session
        self.session = requests.Session()

    def _update_auth_header(self):
        '''Adds the Authorization header to the session'''
        token = get_access_token()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })

    def _request(self, method: str, endpoint: str, **kwargs):
        self._update_auth_header()
        url = f"{self.BASE_URL}{endpoint}"
        r = self.session.request(method, url, **kwargs)

        # Handle 400 errors
        if r.status_code == 400:
            raise requests.HTTPError(
                f"400 from Procore: {r.text}",
                response=r
            )

        if r.status_code == 401:
            # Token expired, refresh and retry once
            auth = ProcoreToken.get_current()
            refresh_tokens(auth)
            self._update_auth_header()
            r = self.session.request(method, url, **kwargs)

        r.raise_for_status()
        return r.json() if r.text else None
    
    def _get(self, endpoint: str, params: Optional[Dict] = None):
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: Dict):
        return self._request("POST", endpoint, json=data)

    def _delete(self, endpoint: str):
        return self._request("DELETE", endpoint)

    # -------------------------
    # Projects
    # -------------------------
    def get_projects(self, company_id: int) -> List[Dict]:
        projects = self._get(f"/rest/v1.1/projects?company_id={company_id}")
        return projects


    # -------------------------
    # Webhooks
    # -------------------------
    def list_project_webhooks(self, project_id: int, namespace: str) -> List[Dict]:
        return self._get(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks?namespace={namespace}")

    def check_for_hooks(self, project_id: int, namespace: str) -> bool:
        webhooks_data = self.list_project_webhooks(project_id, namespace)
        return len(webhooks_data["data"]) > 0

    def create_project_webhook(self, project_id: int, name: str, event_type: str) -> Dict:
        data = {
            "payload_version": "v4.0",
            "namespace": 'mile-high-metal-works',
            "destination_url": self.webhook_url,
        }
        return self._post(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks", data)

    def create_webhook_trigger(self, project_id: int, hook_id: int) -> Dict:
        data = {
            "resource_name": "Submittal",
            "event_type": "update",
        }
        return self._post(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks/{hook_id}/triggers", data)

    def get_project_webhook_resources(self, project_id: int) -> List[Dict]:
        data = {
            "payload_version": "v2.0",
        }
        return self._get(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/resources", data)