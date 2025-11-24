"""Parser for real Apigee Edge exported data"""
import json
import os
from pathlib import Path
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class EdgeDataParser:
    """Parse exported Apigee Edge data from directory structure"""
    
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            # Get the directory where this file is located
            # Go up one level (utils -> backend), then into data_edge
            data_dir = Path(__file__).parent.parent / "data_edge"
        self.data_dir = Path(data_dir)
        
    def parse_all(self) -> Dict[str, Any]:
        """Parse all Edge resources from the data directory"""
        return {
            "proxies": self.parse_proxies(),
            "shared_flows": self.parse_shared_flows(),
            "developers": self.parse_developers(),
            "apps": self.parse_apps(),
            "api_products": self.parse_api_products(),
            "target_servers": self.parse_target_servers(),
            "kvms": self.parse_kvms()
        }
    
    def parse_proxies(self) -> List[Dict[str, Any]]:
        """Parse API proxies"""
        proxies = []
        proxies_dir = self.data_dir / "proxies"
        
        if not proxies_dir.exists():
            return proxies
        
        # Find all .zip files
        for zip_file in proxies_dir.glob("*.zip"):
            proxy_name = zip_file.stem
            proxy_dir = proxies_dir / proxy_name
            
            proxy_data = {
                "name": proxy_name,
                "type": "API Proxy",
                "bundle_path": str(zip_file),
                "policies": [],
                "targets": [],
                "endpoints": []
            }
            
            # Parse proxy details if directory exists
            if proxy_dir.exists():
                # Parse policies
                policies_dir = proxy_dir / "apiproxy" / "policies"
                if policies_dir.exists():
                    for policy_file in policies_dir.glob("*.xml"):
                        policy_data = self._parse_policy(policy_file)
                        if policy_data:
                            proxy_data["policies"].append(policy_data)
                
                # Parse targets
                targets_dir = proxy_dir / "apiproxy" / "targets"
                if targets_dir.exists():
                    for target_file in targets_dir.glob("*.xml"):
                        proxy_data["targets"].append(target_file.stem)
                
                # Parse proxy endpoints
                proxies_endpoint_dir = proxy_dir / "apiproxy" / "proxies"
                if proxies_endpoint_dir.exists():
                    for endpoint_file in proxies_endpoint_dir.glob("*.xml"):
                        proxy_data["endpoints"].append(endpoint_file.stem)
            
            proxy_data["policy_count"] = len(proxy_data["policies"])
            proxies.append(proxy_data)
        
        return proxies
    
    def parse_shared_flows(self) -> List[Dict[str, Any]]:
        """Parse shared flows"""
        flows = []
        flows_dir = self.data_dir / "sharedflows"
        
        if not flows_dir.exists():
            return flows
        
        for zip_file in flows_dir.glob("*.zip"):
            flow_data = {
                "name": zip_file.stem,
                "type": "Shared Flow",
                "bundle_path": str(zip_file)
            }
            flows.append(flow_data)
        
        return flows
    
    def parse_developers(self) -> List[Dict[str, Any]]:
        """Parse developers"""
        developers = []
        devs_dir = self.data_dir / "developers"
        
        if not devs_dir.exists():
            return developers
        
        for dev_file in devs_dir.iterdir():
            if dev_file.is_file():
                try:
                    with open(dev_file, 'r') as f:
                        dev_data = json.load(f)
                        developers.append({
                            "email": dev_data.get("email"),
                            "firstName": dev_data.get("firstName"),
                            "lastName": dev_data.get("lastName"),
                            "userName": dev_data.get("userName"),
                            "status": dev_data.get("status"),
                            "developerId": dev_data.get("developerId"),
                            "organizationName": dev_data.get("organizationName"),
                            "apps": dev_data.get("apps", []),
                            "attributes": dev_data.get("attributes", [])
                        })
                except Exception as e:
                    logger.error(f"Failed to parse developer {dev_file}: {e}")
        
        return developers
    
    def parse_apps(self) -> List[Dict[str, Any]]:
        """Parse developer apps"""
        apps = []
        apps_dir = self.data_dir / "apps"
        
        if not apps_dir.exists():
            return apps
        
        for app_file in apps_dir.iterdir():
            if app_file.is_file():
                try:
                    with open(app_file, 'r') as f:
                        app_data = json.load(f)
                        
                        # Extract API products from credentials
                        api_products = []
                        credentials = app_data.get("credentials", [])
                        for cred in credentials:
                            for prod in cred.get("apiProducts", []):
                                api_products.append(prod.get("apiproduct"))
                        
                        apps.append({
                            "name": app_data.get("name"),
                            "appId": app_data.get("appId"),
                            "developerId": app_data.get("developerId"),
                            "status": app_data.get("status"),
                            "callbackUrl": app_data.get("callbackUrl"),
                            "apiProducts": api_products,
                            "credentials": len(credentials),
                            "attributes": app_data.get("attributes", [])
                        })
                except Exception as e:
                    logger.error(f"Failed to parse app {app_file}: {e}")
        
        return apps
    
    def parse_api_products(self) -> List[Dict[str, Any]]:
        """Parse API products"""
        products = []
        products_dir = self.data_dir / "apiproducts"
        
        if not products_dir.exists():
            return products
        
        for product_file in products_dir.iterdir():
            if product_file.is_file():
                try:
                    with open(product_file, 'r') as f:
                        prod_data = json.load(f)
                        products.append({
                            "name": prod_data.get("name"),
                            "displayName": prod_data.get("displayName"),
                            "description": prod_data.get("description", ""),
                            "approvalType": prod_data.get("approvalType"),
                            "proxies": prod_data.get("proxies", []),
                            "apiResources": prod_data.get("apiResources", []),
                            "scopes": prod_data.get("scopes", []),
                            "attributes": prod_data.get("attributes", []),
                            "environments": prod_data.get("environments", [])
                        })
                except Exception as e:
                    logger.error(f"Failed to parse product {product_file}: {e}")
        
        return products
    
    def parse_target_servers(self) -> List[Dict[str, Any]]:
        """Parse target servers"""
        servers = []
        servers_dir = self.data_dir / "targetservers" / "env"
        
        if not servers_dir.exists():
            return servers
        
        # Iterate through environments
        for env_dir in servers_dir.iterdir():
            if env_dir.is_dir():
                environment = env_dir.name
                for server_file in env_dir.iterdir():
                    if server_file.is_file():
                        try:
                            with open(server_file, 'r') as f:
                                server_data = json.load(f)
                                servers.append({
                                    "name": server_data.get("name"),
                                    "host": server_data.get("host"),
                                    "port": server_data.get("port"),
                                    "isEnabled": server_data.get("isEnabled"),
                                    "environment": environment,
                                    "sslEnabled": server_data.get("sSLInfo", {}).get("enabled") == "true",
                                    "sslInfo": server_data.get("sSLInfo", {})
                                })
                        except Exception as e:
                            logger.error(f"Failed to parse target server {server_file}: {e}")
        
        return servers
    
    def parse_kvms(self) -> List[Dict[str, Any]]:
        """Parse Key-Value Maps"""
        kvms = []
        kvms_dir = self.data_dir / "keyvaluemaps" / "env"
        
        if not kvms_dir.exists():
            return kvms
        
        # Iterate through environments
        for env_dir in kvms_dir.iterdir():
            if env_dir.is_dir():
                environment = env_dir.name
                for kvm_file in env_dir.iterdir():
                    if kvm_file.is_file():
                        try:
                            with open(kvm_file, 'r') as f:
                                kvm_data = json.load(f)
                                kvms.append({
                                    "name": kvm_data.get("name"),
                                    "environment": environment,
                                    "encrypted": kvm_data.get("encrypted", False),
                                    "entries": len(kvm_data.get("entry", []))
                                })
                        except Exception as e:
                            logger.error(f"Failed to parse KVM {kvm_file}: {e}")
        
        return kvms
    
    def _parse_policy(self, policy_file: Path) -> Dict[str, Any]:
        """Parse policy XML file to extract policy type"""
        try:
            # Simple XML parsing to get policy type
            with open(policy_file, 'r') as f:
                content = f.read()
                # Extract policy type from XML root element
                # This is a simplified approach
                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('<') and not line.startswith('<?xml'):
                        # Extract tag name
                        tag = line.split()[0].replace('<', '').replace('>', '')
                        if tag and not tag.startswith('/'):
                            return {
                                "name": policy_file.stem,
                                "type": tag
                            }
            return None
        except Exception as e:
            logger.error(f"Failed to parse policy {policy_file}: {e}")
            return None
    
    def get_summary(self) -> Dict[str, int]:
        """Get summary counts of all resources"""
        data = self.parse_all()
        return {
            "proxies": len(data["proxies"]),
            "shared_flows": len(data["shared_flows"]),
            "developers": len(data["developers"]),
            "apps": len(data["apps"]),
            "api_products": len(data["api_products"]),
            "target_servers": len(data["target_servers"]),
            "kvms": len(data["kvms"]),
            "total": sum([
                len(data["proxies"]),
                len(data["shared_flows"]),
                len(data["developers"]),
                len(data["apps"]),
                len(data["api_products"]),
                len(data["target_servers"]),
                len(data["kvms"])
            ])
        }
