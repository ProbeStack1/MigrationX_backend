"""Calculate differences between Edge and Apigee X resources"""
from typing import Dict, Any, List
from models.migration_models import DiffResult


class DiffCalculator:
    """Calculate and format differences between resources"""
    
    @staticmethod
    def calculate_diff(edge_resource: Dict[str, Any], x_resource: Dict[str, Any], resource_type: str, resource_name: str) -> DiffResult:
        """Calculate differences between Edge and X resources"""
        differences = []
        
        # Compare common fields
        all_keys = set(edge_resource.keys()) | set(x_resource.keys())
        
        for key in all_keys:
            edge_value = edge_resource.get(key)
            x_value = x_resource.get(key)
            
            if edge_value != x_value:
                differences.append({
                    "field": key,
                    "edge_value": edge_value,
                    "x_value": x_value,
                    "change_type": DiffCalculator._get_change_type(edge_value, x_value)
                })
        
        # Determine overall status
        if not differences:
            status = "identical"
        else:
            status = "modified"
        
        return DiffResult(
            resource_type=resource_type,
            resource_name=resource_name,
            differences=differences,
            status=status
        )
    
    @staticmethod
    def _get_change_type(edge_value: Any, x_value: Any) -> str:
        """Determine the type of change"""
        if edge_value is None and x_value is not None:
            return "added"
        elif edge_value is not None and x_value is None:
            return "removed"
        else:
            return "modified"
    
    @staticmethod
    def calculate_policy_diff(edge_policies: List[Dict[str, Any]], x_policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate differences in policies"""
        differences = []
        
        edge_policy_names = {p.get("name") for p in edge_policies}
        x_policy_names = {p.get("name") for p in x_policies}
        
        # Find added policies
        added = x_policy_names - edge_policy_names
        for policy_name in added:
            differences.append({
                "policy_name": policy_name,
                "change_type": "added",
                "description": f"Policy '{policy_name}' was added during transformation"
            })
        
        # Find removed policies
        removed = edge_policy_names - x_policy_names
        for policy_name in removed:
            differences.append({
                "policy_name": policy_name,
                "change_type": "removed",
                "description": f"Policy '{policy_name}' was removed (likely unsupported in Apigee X)"
            })
        
        # Find modified policies
        common = edge_policy_names & x_policy_names
        for policy_name in common:
            edge_policy = next((p for p in edge_policies if p.get("name") == policy_name), None)
            x_policy = next((p for p in x_policies if p.get("name") == policy_name), None)
            
            if edge_policy and x_policy and edge_policy.get("type") != x_policy.get("type"):
                differences.append({
                    "policy_name": policy_name,
                    "change_type": "modified",
                    "description": f"Policy type changed from '{edge_policy.get('type')}' to '{x_policy.get('type')}'"
                })
        
        return differences
