"""Complete migration orchestration with real API calls"""
import logging
from typing import Dict, Any, Tuple, List
import os
import tempfile

from migration.apigee_edge_client import ApigeeEdgeClient
from migration.apigee_x_client import ApigeeXClient

logger = logging.getLogger(__name__)


class CompleteMigrator:
    """Complete migration orchestrator with real API integration"""
    
    def __init__(self, edge_config: Dict[str, Any], apigee_x_config: Dict[str, Any]):
        # Initialize Edge client
        self.edge_client = ApigeeEdgeClient(
            org=edge_config.get("org"),
            username=edge_config.get("username"),
            password=edge_config.get("password"),
            base_url=edge_config.get("base_url", "https://api.enterprise.apigee.com")
        )
        
        # Initialize Apigee X client
        self.x_client = ApigeeXClient(
            project_id=apigee_x_config.get("project_id"),
            org=apigee_x_config.get("organization"),
            service_account_json=apigee_x_config.get("service_account_key"),
            location=apigee_x_config.get("location", "us-central1")
        )
        
        self.edge_env = edge_config.get("environment")
        self.x_env = apigee_x_config.get("environment")
    
    def migrate_target_server(self, target_name: str) -> Tuple[bool, str]:
        """Migrate a single target server"""
        try:
            # Get target server from Edge
            logger.info(f"Fetching target server: {target_name}")
            status, edge_data = self.edge_client.get_target_server(self.edge_env, target_name)
            
            if status != 200:
                return False, f"Failed to fetch from Edge: {edge_data}"
            
            # Create in Apigee X
            logger.info(f"Creating target server in Apigee X: {target_name}")
            status, x_response = self.x_client.create_target_server(self.x_env, edge_data)
            
            if status in [200, 201]:
                return True, f"Target server {target_name} migrated successfully"
            else:
                return False, f"Failed to create in Apigee X: {x_response}"
        
        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            return False, str(e)
    
    def migrate_kvm(self, kvm_name: str, include_entries: bool = True) -> Tuple[bool, str]:
        """Migrate a KVM with its entries"""
        try:
            # Get KVM from Edge
            logger.info(f"Fetching KVM: {kvm_name}")
            status, edge_data = self.edge_client.get_kvm(self.edge_env, kvm_name)
            
            if status != 200:
                return False, f"Failed to fetch from Edge: {edge_data}"
            
            # Create KVM in Apigee X
            logger.info(f"Creating KVM in Apigee X: {kvm_name}")
            status, x_response = self.x_client.create_kvm(self.x_env, edge_data)
            
            if status not in [200, 201]:
                return False, f"Failed to create KVM: {x_response}"
            
            # Migrate entries if requested
            if include_entries:
                logger.info(f"Migrating KVM entries for: {kvm_name}")
                entries_status, entries = self.edge_client.get_kvm_entries(self.edge_env, kvm_name)
                
                if entries_status == 200 and entries:
                    for entry in entries:
                        key = entry.get("name")
                        value = entry.get("value")
                        
                        status, _ = self.x_client.add_kvm_entry(self.x_env, kvm_name, key, value)
                        if status not in [200, 201]:
                            logger.warning(f"Failed to add entry {key} to KVM {kvm_name}")
            
            return True, f"KVM {kvm_name} migrated successfully with entries"
        
        except Exception as e:
            logger.error(f"KVM migration failed: {str(e)}")
            return False, str(e)
    
    def migrate_proxy(self, proxy_name: str, revision: str = None) -> Tuple[bool, str]:
        """Migrate an API proxy"""
        try:
            # Get proxy details
            logger.info(f"Fetching proxy: {proxy_name}")
            status, proxy_data = self.edge_client.get_proxy(proxy_name)
            
            if status != 200:
                return False, f"Failed to fetch proxy: {proxy_data}"
            
            # Get latest revision if not specified
            if not revision:
                revisions = proxy_data.get("revision", [])
                if revisions:
                    revision = revisions[-1] if isinstance(revisions, list) else revisions
                else:
                    return False, "No revisions found for proxy"
            
            # Export proxy bundle
            logger.info(f"Exporting proxy bundle: {proxy_name} revision {revision}")
            status, bundle_data = self.edge_client.export_proxy_bundle(proxy_name, revision)
            
            if status != 200:
                return False, f"Failed to export bundle: {bundle_data}"
            
            # Import to Apigee X
            logger.info(f"Importing proxy to Apigee X: {proxy_name}")
            status, import_response = self.x_client.import_proxy(proxy_name, bundle_data)
            
            if status not in [200, 201]:
                return False, f"Failed to import proxy: {import_response}"
            
            # Get imported revision
            imported_revision = import_response.get("revision", "1")
            
            # Deploy to environment
            logger.info(f"Deploying proxy: {proxy_name} revision {imported_revision}")
            status, deploy_response = self.x_client.deploy_proxy(self.x_env, proxy_name, imported_revision)
            
            if status in [200, 201]:
                return True, f"Proxy {proxy_name} migrated and deployed successfully"
            else:
                return True, f"Proxy {proxy_name} imported but deployment failed: {deploy_response}"
        
        except Exception as e:
            logger.error(f"Proxy migration failed: {str(e)}")
            return False, str(e)
    
    def migrate_api_product(self, product_name: str) -> Tuple[bool, str]:
        """Migrate an API product"""
        try:
            # Get product from Edge
            logger.info(f"Fetching API product: {product_name}")
            status, edge_data = self.edge_client.get_api_product(product_name)
            
            if status != 200:
                return False, f"Failed to fetch product: {edge_data}"
            
            # Create in Apigee X
            logger.info(f"Creating API product in Apigee X: {product_name}")
            status, x_response = self.x_client.create_api_product(edge_data)
            
            if status in [200, 201]:
                return True, f"API product {product_name} migrated successfully"
            else:
                return False, f"Failed to create product: {x_response}"
        
        except Exception as e:
            logger.error(f"Product migration failed: {str(e)}")
            return False, str(e)
    
    def migrate_developer(self, developer_email: str) -> Tuple[bool, str]:
        """Migrate a developer"""
        try:
            # Get developer from Edge
            logger.info(f"Fetching developer: {developer_email}")
            status, edge_data = self.edge_client.get_developer(developer_email)
            
            if status != 200:
                return False, f"Failed to fetch developer: {edge_data}"
            
            # Create in Apigee X
            logger.info(f"Creating developer in Apigee X: {developer_email}")
            status, x_response = self.x_client.create_developer(edge_data)
            
            if status in [200, 201]:
                return True, f"Developer {developer_email} migrated successfully"
            else:
                return False, f"Failed to create developer: {x_response}"
        
        except Exception as e:
            logger.error(f"Developer migration failed: {str(e)}")
            return False, str(e)
    
    def migrate_developer_app(self, developer_email: str, app_name: str) -> Tuple[bool, str]:
        """Migrate a developer app"""
        try:
            # Get app from Edge
            logger.info(f"Fetching developer app: {app_name}")
            status, edge_data = self.edge_client.get_developer_app(developer_email, app_name)
            
            if status != 200:
                return False, f"Failed to fetch app: {edge_data}"
            
            # Create in Apigee X
            logger.info(f"Creating developer app in Apigee X: {app_name}")
            status, x_response = self.x_client.create_developer_app(developer_email, edge_data)
            
            if status in [200, 201]:
                return True, f"Developer app {app_name} migrated successfully"
            else:
                return False, f"Failed to create app: {x_response}"
        
        except Exception as e:
            logger.error(f"App migration failed: {str(e)}")
            return False, str(e)
