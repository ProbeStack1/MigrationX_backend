"""Transform Edge resources to Apigee X compatible format"""
from typing import Dict, Any, List
import logging
from utils.logger import MigrationLogger

logger = logging.getLogger(__name__)


class ResourceTransformer:
    """Transform Apigee Edge resources to Apigee X format"""
    
    # Policies that need transformation or removal
    UNSUPPORTED_POLICIES = [
        "SOAPMessageValidation",
        "XMLToJSON",  # Deprecated in X
        "JSONToXML",  # Deprecated in X
    ]
    
    POLICIES_NEEDING_UPDATE = {
        "JavaCallout": "ExtensionCallout",  # Java callouts → Extension callouts
        "Python": "ExtensionCallout",  # Python scripts → Extension callouts
        "Javascript": "ExtensionCallout",  # Some JS → Extension callouts
    }
    
    def __init__(self, migration_logger: MigrationLogger):
        self.logger = migration_logger
        self.transformation_stats = {
            "policies_removed": 0,
            "policies_transformed": 0,
            "target_servers_updated": 0,
            "kvms_transformed": 0,
        }
    
    def transform_all(self, edge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform all Edge resources to Apigee X format"""
        self.logger.info("Starting resource transformation...")
        
        x_data = {
            "proxies": [],
            "shared_flows": [],
            "target_servers": [],
            "kvms": [],
            "api_products": [],
            "developers": [],
            "developer_apps": [],
        }
        
        try:
            # Transform proxies
            self.logger.info("Transforming API proxies...")
            x_data["proxies"] = [self.transform_proxy(p) for p in edge_data.get("proxies", [])]
            
            # Transform shared flows
            self.logger.info("Transforming shared flows...")
            x_data["shared_flows"] = [self.transform_shared_flow(sf) for sf in edge_data.get("shared_flows", [])]
            
            # Transform target servers
            self.logger.info("Transforming target servers...")
            x_data["target_servers"] = [self.transform_target_server(ts) for ts in edge_data.get("target_servers", [])]
            
            # Transform KVMs
            self.logger.info("Transforming KVMs...")
            x_data["kvms"] = [self.transform_kvm(kvm) for kvm in edge_data.get("kvms", [])]
            
            # API products, developers, and apps need minimal transformation
            x_data["api_products"] = edge_data.get("api_products", [])
            x_data["developers"] = edge_data.get("developers", [])
            x_data["developer_apps"] = edge_data.get("developer_apps", [])
            
            self.logger.success(f"Transformation completed. Stats: {self.transformation_stats}")
            
        except Exception as e:
            self.logger.error(f"Transformation failed: {str(e)}")
            raise
        
        return x_data
    
    def transform_proxy(self, proxy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform API proxy for Apigee X"""
        transformed = proxy_data.copy()
        proxy_name = proxy_data.get("name", "unknown")
        
        # Transform policies
        if "policies" in transformed:
            original_count = len(transformed["policies"])
            transformed["policies"] = self._transform_policies(transformed["policies"])
            new_count = len(transformed["policies"])
            
            if original_count != new_count:
                self.logger.warning(f"Proxy '{proxy_name}': Removed {original_count - new_count} unsupported policies")
        
        # Update target server references if needed
        if "target_servers" in transformed:
            self.transformation_stats["target_servers_updated"] += 1
        
        return transformed
    
    def transform_shared_flow(self, flow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform shared flow for Apigee X"""
        transformed = flow_data.copy()
        flow_name = flow_data.get("name", "unknown")
        
        # Transform policies
        if "policies" in transformed:
            original_count = len(transformed["policies"])
            transformed["policies"] = self._transform_policies(transformed["policies"])
            new_count = len(transformed["policies"])
            
            if original_count != new_count:
                self.logger.warning(f"Shared flow '{flow_name}': Removed {original_count - new_count} unsupported policies")
        
        return transformed
    
    def transform_target_server(self, server_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform target server for Apigee X"""
        transformed = server_data.copy()
        
        # Apigee X uses slightly different structure
        # Add protocol field if missing
        if "protocol" not in transformed:
            port = transformed.get("port", 80)
            transformed["protocol"] = "HTTPS" if port == 443 else "HTTP"
        
        # Update SSL info structure if needed
        if "ssl_info" in transformed and transformed["ssl_info"]:
            ssl_info = transformed["ssl_info"]
            # Ensure TLS 1.2+ only
            if "protocols" in ssl_info:
                ssl_info["protocols"] = [p for p in ssl_info["protocols"] if "TLSv1.2" in p or "TLSv1.3" in p]
                if not ssl_info["protocols"]:
                    ssl_info["protocols"] = ["TLSv1.2", "TLSv1.3"]
        
        self.transformation_stats["target_servers_updated"] += 1
        return transformed
    
    def transform_kvm(self, kvm_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform KVM for Apigee X"""
        transformed = kvm_data.copy()
        
        # Apigee X KVMs have similar structure
        # Main difference is in how entries are stored
        # Edge: entries as {key: value}
        # X: entries as [{name: key, value: value}]
        
        if "entries" in transformed and isinstance(transformed["entries"], dict):
            # Keep as dict for now - will be transformed during import
            pass
        
        self.transformation_stats["kvms_transformed"] += 1
        return transformed
    
    def _transform_policies(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform policy list, removing unsupported and updating others"""
        transformed_policies = []
        
        for policy in policies:
            policy_type = policy.get("type", "")
            policy_name = policy.get("name", "unknown")
            
            # Check if policy is unsupported
            if policy_type in self.UNSUPPORTED_POLICIES:
                self.logger.warning(f"Removing unsupported policy: {policy_name} ({policy_type})")
                self.transformation_stats["policies_removed"] += 1
                continue
            
            # Check if policy needs transformation
            if policy_type in self.POLICIES_NEEDING_UPDATE:
                new_type = self.POLICIES_NEEDING_UPDATE[policy_type]
                self.logger.info(f"Transforming policy: {policy_name} from {policy_type} to {new_type}")
                policy = policy.copy()
                policy["type"] = new_type
                policy["original_type"] = policy_type
                self.transformation_stats["policies_transformed"] += 1
            
            transformed_policies.append(policy)
        
        return transformed_policies
    
    def get_transformation_report(self) -> Dict[str, Any]:
        """Get transformation statistics"""
        return {
            "statistics": self.transformation_stats,
            "warnings": self.logger.get_warnings(),
            "errors": self.logger.get_errors(),
        }
