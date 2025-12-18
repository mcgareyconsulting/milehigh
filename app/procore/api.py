import time
import requests
from typing import Optional, Dict, List
from requests.exceptions import ConnectionError, Timeout, RequestException
from urllib3.exceptions import ProtocolError

from app.config import Config as cfg
from app.procore.procore_auth import get_access_token, get_access_token_force_refresh

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

    def _request(self, method: str, endpoint: str, max_retries: int = 3, retry_delay: float = 1.0, **kwargs):
        """
        Make a request with retry logic for connection errors.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            max_retries: Maximum number of retries for connection errors
            retry_delay: Initial delay between retries (exponential backoff)
            **kwargs: Additional arguments for requests
        """
        self._update_auth_header()
        url = f"{self.BASE_URL}{endpoint}"
        
        last_exception = None
        for attempt in range(max_retries):
            try:
                r = self.session.request(method, url, timeout=30, **kwargs)
                
                # Handle 400 errors
                if r.status_code == 400:
                    raise requests.HTTPError(
                        f"400 from Procore: {r.text}",
                        response=r
                    )

                if r.status_code == 401:
                    # Token expired or invalid, force refresh once
                    get_access_token_force_refresh()
                    self._update_auth_header()
                    r = self.session.request(method, url, timeout=30, **kwargs)

                r.raise_for_status()
                return r.json() if r.text else None
                
            except (ConnectionError, ProtocolError, Timeout) as e:
                # Connection errors - retry with exponential backoff
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    time.sleep(wait_time)
                    continue
                else:
                    # Max retries reached, raise the exception
                    raise requests.ConnectionError(
                        f"Connection error after {max_retries} attempts: {str(e)}"
                    ) from e
            except requests.HTTPError:
                # HTTP errors (4xx, 5xx) - don't retry
                raise
            except RequestException as e:
                # Other request exceptions - don't retry
                raise
        
        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
    
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
    # Submittals
    # -------------------------
    def get_submittals(self, project_id: int) -> List[Dict]:
        return self._get(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/submittals")

    def get_submittal_by_id(self, project_id: int, submittal_id: int) -> Dict:
        return self._get(f"/rest/v1.1/projects/{project_id}/submittals/{submittal_id}")

    def get_sub_filters_by_project_id(self, project_id: int) -> List[Dict]:
        return self._get(f"/rest/v1.0/projects/{project_id}/submittals/filter_options/status_id")

    def get_submittals_for_drafting_workload(self, project_id: int) -> List[Dict]:
        # Known filters for drafting workload:
        # status: Open
        # type: 2 = Drafting Release Review
        # type: 3 = Submittal For Gc  Approval
        return self._get(f"/rest/v1.1/projects/{project_id}/submittals?filters[type][]=Drafting Release Review&filters[type][]=Submittal for GC  Approval&filter[type][]=Submittal for GC Approval&filters[status_id]=203238")
    # -------------------------
    # Webhooks
    # -------------------------
    def list_project_webhooks(self, project_id: int, namespace: str) -> List[Dict]:
        """List webhooks for a project. Returns a list of webhooks."""
        response = self._get(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks?namespace={namespace}")
        # Procore API returns {"data": [...]} format, extract the list
        if isinstance(response, dict) and "data" in response:
            return response["data"] if response["data"] else []
        elif isinstance(response, list):
            return response
        return []

    def create_project_webhook(self, project_id: int, name: str, event_type: str) -> Dict:
        data = {
            "payload_version": "v4.0",
            "namespace": 'mile-high-metal-works',
            "destination_url": self.webhook_url,
        }
        return self._post(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks", data)

    def create_webhook_trigger(self, project_id: int, hook_id: int, event_type: str) -> Dict:
        data = {
            "resource_name": "Submittals",
            "event_type": event_type,
        }
        return self._post(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks/{hook_id}/triggers", data)

    def get_webhook_details(self, project_id: int, hook_id: int) -> Dict:
        """Get details of a specific webhook including its triggers."""
        return self._get(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks/{hook_id}")

    def get_webhook_triggers(self, project_id: int, hook_id: int) -> List[Dict]:
        """Get triggers for a specific webhook."""
        response = self._get(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks/{hook_id}/triggers")
        # Procore API returns {"data": [...]} format, extract the list
        if isinstance(response, dict) and "data" in response:
            return response["data"] if response["data"] else []
        elif isinstance(response, list):
            return response
        return []

    def get_deliveries(self, company_id: int, project_id: int, hook_id: int) -> List[Dict]:
        """
        Get deliveries for a specific webhook.
        
        Note: Deliveries may not exist until webhooks have been triggered.
        Returns empty list if 404 (webhook exists but no deliveries yet).
        """
        try:
            response = self._get(f"/rest/v2.0/companies/{company_id}/projects/{project_id}/webhooks/hooks/{hook_id}/deliveries")
            # Procore API returns {"data": [...]} format, extract the list
            if isinstance(response, dict) and "data" in response:
                return response["data"] if response["data"] else []
            elif isinstance(response, list):
                return response
            return []
        except requests.HTTPError as e:
            # If 404, webhook exists but no deliveries yet (normal for new webhooks)
            if e.response and e.response.status_code == 404:
                return []
            # Re-raise other HTTP errors
            raise

    def get_webhook_deliveries(self, company_id: int, project_id: int, hook_id: int) -> List[Dict]:
        """Alias for get_deliveries() for backward compatibility."""
        return self.get_deliveries(company_id, project_id, hook_id)

    def delete_webhook(self, project_id: int, hook_id: int) -> Dict:
        """Delete a specific webhook."""
        return self._delete(f"/rest/v2.0/companies/{cfg.PROD_PROCORE_COMPANY_ID}/projects/{project_id}/webhooks/hooks/{hook_id}")