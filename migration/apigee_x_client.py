"""Complete Apigee X API client implementation"""
import requests
import json
import logging
from typing import Dict, Any, Optional, Tuple
from google.oauth2 import service_account
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)


class ApigeeXClient:
    """Complete client for Apigee X Management API (GCP)"""
    
    def __init__(self, project_id: str, org: str, service_account_json: str, location: str = "us-central1"):
        self.project_id = project_id
        self.org = org
        self.location = location
        self.base_url = f"https://apigee.googleapis.com/v1/organizations/{org}"
        
        # Initialize credentials
        try:
            service_account_info = json.loads(service_account_json)
            self.credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
        except Exception as e:
            logger.error(f"Failed to load service account: {str(e)}")
            self.credentials = None
        
        self.session = requests.Session()
    
    def _get_access_token(self) -> Optional[str]:
        """Get access token from service account"""
        if not self.credentials:
            return None
        
        try:
            if not self.credentials.valid:
                self.credentials.refresh(Request())
            return self.credentials.token
        except Exception as e:
            logger.error(f"Failed to get access token: {str(e)}")
            return None
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Tuple[int, Any]:
        """Make HTTP request to Apigee X API"""
        url = f"{self.base_url}/{endpoint}"
        
        token = self._get_access_token()
        if not token:
            return 401, {"error": "Failed to get access token"}
        
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        
        try:
            response = self.session.request(method, url, **kwargs)
            
            if response.status_code in [200, 201]:
                try:
                    return response.status_code, response.json()
                except:
                    return response.status_code, {"message": "Success"}
            else:
                return response.status_code, {"error": response.text}
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return 500, {"error": str(e)}
    
    def create_target_server(self, env: str, target_server_data: Dict[str, Any]) -> Tuple[int, Any]:
        """Create target server in Apigee X"""
        endpoint = f"environments/{env}/targetservers"
        
        payload = {
            "name": target_server_data.get("name"),
            "host": target_server_data.get("host"),
            "port": target_server_data.get("port"),
            "isEnabled": target_server_data.get("isEnabled", True)
        }
        
        # Add SSL info if present
        if target_server_data.get("sSLInfo"):
            payload["sSLInfo"] = target_server_data["sSLInfo"]
        
        return self._make_request("POST", endpoint, json=payload)
    
    def create_kvm(self, env: str, kvm_data: Dict[str, Any]) -> Tuple[int, Any]:
        """Create KVM in Apigee X"""
        endpoint = f"environments/{env}/keyvaluemaps"
        
        payload = {
            "name": kvm_data.get("name"),
            "encrypted": kvm_data.get("encrypted", False)
        }
        
        return self._make_request("POST", endpoint, json=payload)
    
    def add_kvm_entry(self, env: str, kvm_name: str, key: str, value: str) -> Tuple[int, Any]:
        """Add entry to KVM"""
        endpoint = f"environments/{env}/keyvaluemaps/{kvm_name}/entries"
        
        payload = {
            "name": key,
            "value": value
        }
        
        return self._make_request("POST", endpoint, json=payload)
    
    def import_proxy(self, proxy_name: str, bundle_data: bytes) -> Tuple[int, Any]:
        """Import API proxy bundle"""
        endpoint = f"apis?name={proxy_name}&action=import"
        
        token = self._get_access_token()
        if not token:
            return 401, {"error": "Failed to get access token"}
        
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        files = {'file': (f'{proxy_name}.zip', bundle_data, 'application/zip')}
        
        try:
            response = requests.post(url, headers=headers, files=files)
            
            if response.status_code in [200, 201]:
                try:
                    return response.status_code, response.json()
                except:
                    return response.status_code, {"message": "Success"}
            else:
                return response.status_code, {"error": response.text}
        except Exception as e:
            logger.error(f"Import failed: {str(e)}")
            return 500, {"error": str(e)}
    
    def deploy_proxy(self, env: str, proxy_name: str, revision: str) -> Tuple[int, Any]:
        """Deploy API proxy to environment"""
        endpoint = f"environments/{env}/apis/{proxy_name}/revisions/{revision}/deployments"
        
        return self._make_request("POST", endpoint)
    
    def create_api_product(self, product_data: Dict[str, Any]) -> Tuple[int, Any]:
        """Create API product"""
        endpoint = "apiproducts"
        
        # Clean up product data for Apigee X
        payload = {
            "name": product_data.get("name"),
            "displayName": product_data.get("displayName"),
            "description": product_data.get("description", ""),
            "approvalType": product_data.get("approvalType", "auto"),
            "proxies": product_data.get("proxies", []),
            "apiResources": product_data.get("apiResources", []),
            "scopes": product_data.get("scopes", []),
            "environments": product_data.get("environments", [])
        }
        
        # Add attributes if present
        if product_data.get("attributes"):
            payload["attributes"] = product_data["attributes"]
        
        return self._make_request("POST", endpoint, json=payload)
    
    def create_developer(self, developer_data: Dict[str, Any]) -> Tuple[int, Any]:
        """Create developer"""
        endpoint = "developers"
        
        payload = {
            "email": developer_data.get("email"),
            "firstName": developer_data.get("firstName"),
            "lastName": developer_data.get("lastName"),
            "userName": developer_data.get("userName")
        }
        
        if developer_data.get("attributes"):
            payload["attributes"] = developer_data["attributes"]
        
        return self._make_request("POST", endpoint, json=payload)
    
    def create_developer_app(self, developer_email: str, app_data: Dict[str, Any]) -> Tuple[int, Any]:
        """Create developer app"""
        endpoint = f"developers/{developer_email}/apps"
        
        payload = {
            "name": app_data.get("name"),
            "apiProducts": app_data.get("apiProducts", []),
            "callbackUrl": app_data.get("callbackUrl", "")
        }
        
        if app_data.get("attributes"):
            payload["attributes"] = app_data["attributes"]
        
        return self._make_request("POST", endpoint, json=payload)
