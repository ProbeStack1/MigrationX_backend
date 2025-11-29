"""Complete Apigee Edge API client implementation"""
import requests
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
import base64

logger = logging.getLogger(__name__)


class ApigeeEdgeClient:
    """Complete client for Apigee Edge Management API"""
    
    def __init__(self, org: str, username: str, password: str, base_url: str = "https://api.enterprise.apigee.com"):
        self.org = org
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        
        # Set up basic auth
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json"
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Tuple[int, Dict[str, Any]]:
        """Make HTTP request to Edge API"""
        url = f"{self.base_url}/v1/organizations/{self.org}/{endpoint}"
        
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
    
    def get_proxy(self, proxy_name: str) -> Tuple[int, Dict[str, Any]]:
        """Get proxy details"""
        return self._make_request("GET", f"apis/{proxy_name}")
    
    def export_proxy_bundle(self, proxy_name: str, revision: str) -> Tuple[int, bytes]:
        """Export proxy bundle as zip"""
        url = f"{self.base_url}/v1/organizations/{self.org}/apis/{proxy_name}/revisions/{revision}?format=bundle"
        
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return 200, response.content
            else:
                return response.status_code, response.text.encode()
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            return 500, str(e).encode()
    
    def get_target_server(self, env: str, target_name: str) -> Tuple[int, Dict[str, Any]]:
        """Get target server details"""
        return self._make_request("GET", f"environments/{env}/targetservers/{target_name}")
    
    def get_kvm(self, env: str, kvm_name: str) -> Tuple[int, Dict[str, Any]]:
        """Get KVM details"""
        return self._make_request("GET", f"environments/{env}/keyvaluemaps/{kvm_name}")
    
    def get_kvm_entries(self, env: str, kvm_name: str) -> Tuple[int, List[Dict[str, Any]]]:
        """Get KVM entries"""
        status, response = self._make_request("GET", f"environments/{env}/keyvaluemaps/{kvm_name}/entries")
        if status == 200:
            return status, response.get("keyValueEntries", [])
        return status, []
    
    def get_api_product(self, product_name: str) -> Tuple[int, Dict[str, Any]]:
        """Get API product details"""
        return self._make_request("GET", f"apiproducts/{product_name}")
    
    def get_developer(self, developer_email: str) -> Tuple[int, Dict[str, Any]]:
        """Get developer details"""
        return self._make_request("GET", f"developers/{developer_email}")
    
    def get_developer_app(self, developer_email: str, app_name: str) -> Tuple[int, Dict[str, Any]]:
        """Get developer app details"""
        return self._make_request("GET", f"developers/{developer_email}/apps/{app_name}")
    
    def verify_connection(self) -> Tuple[bool, str]:
        """
        Verify connection to Apigee Edge by making a simple API call.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Try to get organization info - a lightweight endpoint that validates auth
            status_code, response = self._make_request("GET", "")
            
            if status_code == 200:
                return True, "Connection verified successfully"
            elif status_code == 401:
                return False, "Authentication failed: Invalid credentials"
            elif status_code == 403:
                return False, "Authorization failed: Insufficient permissions"
            elif status_code == 404:
                return False, f"Organization '{self.org}' not found"
            else:
                error_msg = response.get("error", f"HTTP {status_code}")
                return False, f"Connection failed: {error_msg}"
        except requests.exceptions.ConnectionError as e:
            return False, f"Network error: Unable to reach {self.base_url}"
        except requests.exceptions.Timeout as e:
            return False, f"Connection timeout: {self.base_url} did not respond"
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            return False, f"Verification error: {str(e)}"