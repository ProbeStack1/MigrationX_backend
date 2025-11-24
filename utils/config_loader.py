"""Configuration loader for migration settings"""
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from models.edge_models import EdgeOrgConfig
from models.apigee_x_models import ApigeeXConfig


class ConfigLoader:
    """Load and manage migration configuration"""
    
    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON or YAML file"""
        path = Path(config_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(path, 'r') as f:
            if path.suffix == '.json':
                return json.load(f)
            elif path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported config file format: {path.suffix}")
    
    @staticmethod
    def load_edge_config(config_data: Dict[str, Any]) -> EdgeOrgConfig:
        """Load Edge configuration"""
        edge_config = config_data.get('edge', {})
        return EdgeOrgConfig(**edge_config)
    
    @staticmethod
    def load_apigee_x_config(config_data: Dict[str, Any]) -> ApigeeXConfig:
        """Load Apigee X configuration"""
        x_config = config_data.get('apigee_x', {})
        return ApigeeXConfig(**x_config)
    
    @staticmethod
    def create_default_config() -> Dict[str, Any]:
        """Create a default configuration template"""
        return {
            "edge": {
                "name": "demo-edge-org",
                "base_url": "https://api.enterprise.apigee.com",
                "username": "your-username",
                "password": "your-password",
                "environments": ["prod", "test"]
            },
            "apigee_x": {
                "project_id": "your-gcp-project",
                "organization": "your-apigee-x-org",
                "location": "us-central1",
                "service_account_key_path": "/path/to/service-account-key.json",
                "environments": ["prod", "test"]
            },
            "migration": {
                "batch_size": 10,
                "parallel_imports": True,
                "max_workers": 5,
                "dry_run": False,
                "resource_types": [
                    "proxies",
                    "shared_flows",
                    "target_servers",
                    "kvms",
                    "api_products",
                    "developers",
                    "developer_apps"
                ]
            },
            "transformations": {
                "remove_unsupported_policies": True,
                "convert_java_callouts": True,
                "update_target_servers": True,
                "preserve_revision_history": True
            }
        }
    
    @staticmethod
    def save_config(config_data: Dict[str, Any], output_path: str):
        """Save configuration to file"""
        path = Path(output_path)
        
        with open(path, 'w') as f:
            if path.suffix == '.json':
                json.dump(config_data, f, indent=2)
            elif path.suffix in ['.yaml', '.yml']:
                yaml.dump(config_data, f, default_flow_style=False)
            else:
                raise ValueError(f"Unsupported config file format: {path.suffix}")
