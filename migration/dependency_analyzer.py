"""Analyze dependencies between Apigee resources"""
from typing import Dict, List, Any, Set
import logging

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Analyze and track dependencies between resources"""
    
    def __init__(self):
        self.dependencies = {}
    
    def analyze_dependencies(self, edge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze all resource dependencies"""
        dependencies = {}
        
        # Analyze proxy dependencies
        for proxy in edge_data.get("proxies", []):
            proxy_name = proxy.get("name")
            deps = self._analyze_proxy_dependencies(proxy, edge_data)
            if deps:
                dependencies[proxy_name] = deps
        
        # Analyze API product dependencies
        for product in edge_data.get("api_products", []):
            product_name = product.get("name")
            deps = self._analyze_product_dependencies(product)
            if deps:
                dependencies[product_name] = deps
        
        # Analyze app dependencies
        for app in edge_data.get("apps", []):
            app_name = app.get("name")
            deps = self._analyze_app_dependencies(app)
            if deps:
                dependencies[app_name] = deps
        
        return dependencies
    
    def _analyze_proxy_dependencies(self, proxy: Dict[str, Any], edge_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """Analyze dependencies for a proxy"""
        dependencies = {
            "target_servers": [],
            "kvms": [],
            "shared_flows": []
        }
        
        # Extract target servers from proxy configuration
        target_servers = proxy.get("target_servers", [])
        dependencies["target_servers"] = target_servers
        
        # Extract KVMs used in policies
        policies = proxy.get("policies", [])
        for policy in policies:
            policy_type = policy.get("type", "")
            if policy_type == "KeyValueMapOperations":
                # KVM is used
                kvm_name = policy.get("name", "").replace("KVM-", "")
                if kvm_name and kvm_name not in dependencies["kvms"]:
                    dependencies["kvms"].append(kvm_name)
        
        # Check for shared flow callouts
        for policy in policies:
            if policy.get("type") == "FlowCallout":
                flow_name = policy.get("name", "")
                if flow_name and flow_name not in dependencies["shared_flows"]:
                    dependencies["shared_flows"].append(flow_name)
        
        # Remove empty dependency lists
        dependencies = {k: v for k, v in dependencies.items() if v}
        
        return dependencies
    
    def _analyze_product_dependencies(self, product: Dict[str, Any]) -> Dict[str, List[str]]:
        """Analyze dependencies for an API product"""
        dependencies = {
            "proxies": product.get("proxies", [])
        }
        
        dependencies = {k: v for k, v in dependencies.items() if v}
        return dependencies
    
    def _analyze_app_dependencies(self, app: Dict[str, Any]) -> Dict[str, List[str]]:
        """Analyze dependencies for an app"""
        dependencies = {
            "api_products": app.get("apiProducts", []),
            "developer": [app.get("developerId", "")]
        }
        
        dependencies = {k: v for k, v in dependencies.items() if v}
        return dependencies
    
    def get_migration_order(self, dependencies: Dict[str, Any]) -> List[str]:
        """Determine the correct order for migration based on dependencies"""
        # Base order: Target Servers -> KVMs -> Shared Flows -> Proxies -> Products -> Developers -> Apps
        migration_order = [
            "target_servers",
            "kvms",
            "shared_flows",
            "proxies",
            "api_products",
            "developers",
            "apps"
        ]
        
        return migration_order
    
    def get_resource_dependencies_text(self, resource_name: str, dependencies: Dict[str, Any]) -> str:
        """Get human-readable dependency text for a resource"""
        if resource_name not in dependencies:
            return "No dependencies"
        
        deps = dependencies[resource_name]
        dep_texts = []
        
        if "target_servers" in deps and deps["target_servers"]:
            dep_texts.append(f"Target Servers: {', '.join(deps['target_servers'])}")
        
        if "kvms" in deps and deps["kvms"]:
            dep_texts.append(f"KVMs: {', '.join(deps['kvms'])}")
        
        if "shared_flows" in deps and deps["shared_flows"]:
            dep_texts.append(f"Shared Flows: {', '.join(deps['shared_flows'])}")
        
        if "proxies" in deps and deps["proxies"]:
            dep_texts.append(f"Proxies: {', '.join(deps['proxies'])}")
        
        if "api_products" in deps and deps["api_products"]:
            dep_texts.append(f"API Products: {', '.join(deps['api_products'])}")
        
        if dep_texts:
            return " | ".join(dep_texts)
        
        return "No dependencies"
