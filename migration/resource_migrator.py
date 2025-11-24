"""Individual resource migration functionality"""
import logging
import json
import requests
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


class ResourceMigrator:
    """Migrate individual resources from Edge to Apigee X"""
    
    def __init__(self, apigee_x_config: Dict[str, Any], mock_mode: bool = True):
        self.config = apigee_x_config
        self.mock_mode = mock_mode
        self.org = apigee_x_config.get("organization")
        self.env = apigee_x_config.get("environment")
        self.token = apigee_x_config.get("token", "")
        self.base_url = f"https://apigee.googleapis.com/v1/organizations/{self.org}"
    
    def migrate_target_server(self, target_server_data: Dict[str, Any]) -> Tuple[int, str]:
        """Migrate a single target server"""
        if self.mock_mode:
            logger.info(f"Mock: Migrating target server {target_server_data.get('name')}")
            return 200, json.dumps({"success": True, "message": "Target server migrated (mock)"})
        
        try:
            url = f"{self.base_url}/environments/{self.env}/targetservers"
            
            # Prepare payload
            payload = {
                "name": target_server_data.get("name"),
                "host": target_server_data.get("host"),
                "port": target_server_data.get("port"),
                "isEnabled": target_server_data.get("isEnabled", True)
            }
            
            if target_server_data.get("sslInfo"):
                payload["sSLInfo"] = target_server_data["sslInfo"]
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            return response.status_code, response.text
            
        except Exception as e:
            logger.error(f"Failed to migrate target server: {str(e)}")
            return 500, json.dumps({"error": str(e)})
    
    def migrate_kvm(self, kvm_data: Dict[str, Any]) -> Tuple[int, str]:
        """Migrate a single KVM"""
        if self.mock_mode:
            logger.info(f"Mock: Migrating KVM {kvm_data.get('name')}")
            return 200, json.dumps({"success": True, "message": "KVM migrated (mock)"})
        
        try:
            url = f"{self.base_url}/environments/{self.env}/keyvaluemaps"
            
            payload = {
                "name": kvm_data.get("name"),
                "encrypted": kvm_data.get("encrypted", False)
            }
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            return response.status_code, response.text
            
        except Exception as e:
            logger.error(f"Failed to migrate KVM: {str(e)}")
            return 500, json.dumps({"error": str(e)})
    
    def migrate_proxy(self, proxy_data: Dict[str, Any], bundle_path: str) -> Tuple[int, str]:
        """Migrate a single API proxy"""
        if self.mock_mode:
            logger.info(f"Mock: Migrating proxy {proxy_data.get('name')}")
            return 200, json.dumps({"success": True, "message": "Proxy migrated (mock)"})
        
        try:
            proxy_name = proxy_data.get("name")
            url = f"{self.base_url}/apis?name={proxy_name}&action=import"
            
            headers = {
                "Authorization": f"Bearer {self.token}"
            }
            
            # Read bundle file
            with open(bundle_path, 'rb') as f:
                files = {'file': (f'{proxy_name}.zip', f, 'application/zip')}
                response = requests.post(url, headers=headers, files=files)
            
            return response.status_code, response.text
            
        except Exception as e:
            logger.error(f"Failed to migrate proxy: {str(e)}")
            return 500, json.dumps({"error": str(e)})
    
    def migrate_api_product(self, product_data: Dict[str, Any]) -> Tuple[int, str]:
        """Migrate a single API product"""
        if self.mock_mode:
            logger.info(f"Mock: Migrating API product {product_data.get('name')}")
            return 200, json.dumps({"success": True, "message": "API product migrated (mock)"})
        
        try:
            url = f"{self.base_url}/apiproducts"
            
            # Clean up the product data
            payload = {
                "name": product_data.get("name"),
                "displayName": product_data.get("displayName"),
                "description": product_data.get("description", ""),
                "approvalType": product_data.get("approvalType", "auto"),
                "proxies": product_data.get("proxies", []),
                "apiResources": product_data.get("apiResources", []),
                "scopes": product_data.get("scopes", []),
                "attributes": product_data.get("attributes", []),
                "environments": product_data.get("environments", [])
            }
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            return response.status_code, response.text
            
        except Exception as e:
            logger.error(f"Failed to migrate API product: {str(e)}")
            return 500, json.dumps({"error": str(e)})
