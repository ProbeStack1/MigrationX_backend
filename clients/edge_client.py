"""Apigee Edge API client"""
import requests
from typing import List, Dict, Any, Optional
import json
import logging
from models.edge_models import EdgeProxy, EdgeSharedFlow, EdgeTargetServer, EdgeKVM, EdgeAPIProduct, EdgeDeveloper, EdgeDeveloperApp
from utils.mock_data import MockDataGenerator

logger = logging.getLogger(__name__)


class EdgeClient:
    """Client for interacting with Apigee Edge Management API"""
    
    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None, 
                 token: Optional[str] = None, org: str = "", mock_mode: bool = True):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token = token
        self.org = org
        self.mock_mode = mock_mode
        self.mock_generator = MockDataGenerator()
        self.session = requests.Session()
        
        if not mock_mode:
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
            elif username and password:
                self.session.auth = (username, password)
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to Edge API"""
        if self.mock_mode:
            logger.info(f"Mock mode: Simulating {method} {endpoint}")
            return {"success": True, "mock": True}
        
        url = f"{self.base_url}/v1/organizations/{self.org}/{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    
    def list_proxies(self) -> List[str]:
        """List all API proxies in the organization"""
        if self.mock_mode:
            return [p.name for p in self.mock_generator.generate_proxies()]
        
        data = self._make_request("GET", "apis")
        return data if isinstance(data, list) else []
    
    def get_proxy(self, proxy_name: str, revision: Optional[str] = None) -> Dict[str, Any]:
        """Get API proxy details"""
        if self.mock_mode:
            proxies = self.mock_generator.generate_proxies()
            proxy = next((p for p in proxies if p.name == proxy_name), proxies[0])
            return proxy.model_dump()
        
        endpoint = f"apis/{proxy_name}"
        if revision:
            endpoint += f"/revisions/{revision}"
        return self._make_request("GET", endpoint)
    
    def export_proxy(self, proxy_name: str, revision: str) -> bytes:
        """Export API proxy bundle"""
        if self.mock_mode:
            logger.info(f"Mock: Exporting proxy {proxy_name} revision {revision}")
            return b"mock-proxy-bundle-data"
        
        endpoint = f"apis/{proxy_name}/revisions/{revision}?format=bundle"
        url = f"{self.base_url}/v1/organizations/{self.org}/{endpoint}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.content
    
    def list_shared_flows(self) -> List[str]:
        """List all shared flows"""
        if self.mock_mode:
            return [sf.name for sf in self.mock_generator.generate_shared_flows()]
        
        data = self._make_request("GET", "sharedflows")
        return data if isinstance(data, list) else []
    
    def get_shared_flow(self, flow_name: str) -> Dict[str, Any]:
        """Get shared flow details"""
        if self.mock_mode:
            flows = self.mock_generator.generate_shared_flows()
            flow = next((f for f in flows if f.name == flow_name), flows[0])
            return flow.model_dump()
        
        return self._make_request("GET", f"sharedflows/{flow_name}")
    
    def list_target_servers(self, environment: str) -> List[str]:
        """List target servers in an environment"""
        if self.mock_mode:
            return [ts.name for ts in self.mock_generator.generate_target_servers()]
        
        data = self._make_request("GET", f"environments/{environment}/targetservers")
        return data if isinstance(data, list) else []
    
    def get_target_server(self, environment: str, server_name: str) -> Dict[str, Any]:
        """Get target server details"""
        if self.mock_mode:
            servers = self.mock_generator.generate_target_servers()
            server = next((s for s in servers if s.name == server_name), servers[0])
            return server.model_dump()
        
        return self._make_request("GET", f"environments/{environment}/targetservers/{server_name}")
    
    def list_kvms(self, environment: str) -> List[str]:
        """List KVMs in an environment"""
        if self.mock_mode:
            return [kvm.name for kvm in self.mock_generator.generate_kvms()]
        
        data = self._make_request("GET", f"environments/{environment}/keyvaluemaps")
        return data if isinstance(data, list) else []
    
    def get_kvm(self, environment: str, kvm_name: str) -> Dict[str, Any]:
        """Get KVM details including entries"""
        if self.mock_mode:
            kvms = self.mock_generator.generate_kvms()
            kvm = next((k for k in kvms if k.name == kvm_name), kvms[0])
            return kvm.model_dump()
        
        return self._make_request("GET", f"environments/{environment}/keyvaluemaps/{kvm_name}")
    
    def list_api_products(self) -> List[str]:
        """List all API products"""
        if self.mock_mode:
            return [ap.name for ap in self.mock_generator.generate_api_products()]
        
        data = self._make_request("GET", "apiproducts")
        return data if isinstance(data, list) else []
    
    def get_api_product(self, product_name: str) -> Dict[str, Any]:
        """Get API product details"""
        if self.mock_mode:
            products = self.mock_generator.generate_api_products()
            product = next((p for p in products if p.name == product_name), products[0])
            return product.model_dump()
        
        return self._make_request("GET", f"apiproducts/{product_name}")
    
    def list_developers(self) -> List[str]:
        """List all developers"""
        if self.mock_mode:
            return [d.email for d in self.mock_generator.generate_developers()]
        
        data = self._make_request("GET", "developers")
        return [d.get("email") for d in data] if isinstance(data, list) else []
    
    def get_developer(self, developer_email: str) -> Dict[str, Any]:
        """Get developer details"""
        if self.mock_mode:
            developers = self.mock_generator.generate_developers()
            developer = next((d for d in developers if d.email == developer_email), developers[0])
            return developer.model_dump()
        
        return self._make_request("GET", f"developers/{developer_email}")
    
    def list_developer_apps(self, developer_email: str) -> List[str]:
        """List apps for a developer"""
        if self.mock_mode:
            apps = self.mock_generator.generate_developer_apps()
            return [app.name for app in apps if app.developer_email == developer_email]
        
        data = self._make_request("GET", f"developers/{developer_email}/apps")
        return data if isinstance(data, list) else []
    
    def get_developer_app(self, developer_email: str, app_name: str) -> Dict[str, Any]:
        """Get developer app details"""
        if self.mock_mode:
            apps = self.mock_generator.generate_developer_apps()
            app = next((a for a in apps if a.name == app_name), apps[0])
            return app.model_dump()
        
        return self._make_request("GET", f"developers/{developer_email}/apps/{app_name}")
    
    def list_environments(self) -> List[str]:
        """List all environments"""
        if self.mock_mode:
            return ["prod", "test"]
        
        data = self._make_request("GET", "environments")
        return data if isinstance(data, list) else []
