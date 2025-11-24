"""Export resources from Apigee Edge"""
import asyncio
from typing import List, Dict, Any
import logging
from clients.edge_client import EdgeClient
from models.edge_models import EdgeProxy, EdgeSharedFlow, EdgeTargetServer, EdgeKVM
from utils.logger import MigrationLogger

logger = logging.getLogger(__name__)


class EdgeExporter:
    """Export all resources from Apigee Edge organization"""
    
    def __init__(self, edge_client: EdgeClient, migration_logger: MigrationLogger):
        self.client = edge_client
        self.logger = migration_logger
    
    async def export_all(self, environment: str) -> Dict[str, Any]:
        """Export all resources from Edge"""
        self.logger.info(f"Starting export from Edge org: {self.client.org}, env: {environment}")
        
        export_data = {
            "proxies": [],
            "shared_flows": [],
            "target_servers": [],
            "kvms": [],
            "api_products": [],
            "developers": [],
            "developer_apps": [],
            "environments": []
        }
        
        try:
            # Export proxies
            self.logger.info("Exporting API proxies...")
            export_data["proxies"] = await self.export_proxies()
            
            # Export shared flows
            self.logger.info("Exporting shared flows...")
            export_data["shared_flows"] = await self.export_shared_flows()
            
            # Export target servers
            self.logger.info("Exporting target servers...")
            export_data["target_servers"] = await self.export_target_servers(environment)
            
            # Export KVMs
            self.logger.info("Exporting KVMs...")
            export_data["kvms"] = await self.export_kvms(environment)
            
            # Export API products
            self.logger.info("Exporting API products...")
            export_data["api_products"] = await self.export_api_products()
            
            # Export developers
            self.logger.info("Exporting developers...")
            export_data["developers"] = await self.export_developers()
            
            # Export developer apps
            self.logger.info("Exporting developer apps...")
            export_data["developer_apps"] = await self.export_developer_apps()
            
            self.logger.success(f"Export completed successfully. Total resources: {self._count_resources(export_data)}")
            
        except Exception as e:
            self.logger.error(f"Export failed: {str(e)}")
            raise
        
        return export_data
    
    async def export_proxies(self) -> List[Dict[str, Any]]:
        """Export all API proxies"""
        proxies = []
        try:
            proxy_names = self.client.list_proxies()
            self.logger.info(f"Found {len(proxy_names)} proxies to export")
            
            for proxy_name in proxy_names:
                try:
                    proxy_data = self.client.get_proxy(proxy_name)
                    proxies.append(proxy_data)
                    self.logger.info(f"Exported proxy: {proxy_name}")
                except Exception as e:
                    self.logger.error(f"Failed to export proxy {proxy_name}: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"Failed to list proxies: {str(e)}")
        
        return proxies
    
    async def export_shared_flows(self) -> List[Dict[str, Any]]:
        """Export all shared flows"""
        flows = []
        try:
            flow_names = self.client.list_shared_flows()
            self.logger.info(f"Found {len(flow_names)} shared flows to export")
            
            for flow_name in flow_names:
                try:
                    flow_data = self.client.get_shared_flow(flow_name)
                    flows.append(flow_data)
                    self.logger.info(f"Exported shared flow: {flow_name}")
                except Exception as e:
                    self.logger.error(f"Failed to export shared flow {flow_name}: {str(e)}")
        
        except Exception as e:
            self.logger.error(f"Failed to list shared flows: {str(e)}")
        
        return flows
    
    async def export_target_servers(self, environment: str) -> List[Dict[str, Any]]:
        """Export target servers from environment"""
        servers = []
        try:
            server_names = self.client.list_target_servers(environment)
            self.logger.info(f"Found {len(server_names)} target servers in {environment}")
            
            for server_name in server_names:
                try:
                    server_data = self.client.get_target_server(environment, server_name)
                    servers.append(server_data)
                    self.logger.info(f"Exported target server: {server_name}")
                except Exception as e:
                    self.logger.error(f"Failed to export target server {server_name}: {str(e)}")
        
        except Exception as e:
            self.logger.error(f"Failed to list target servers: {str(e)}")
        
        return servers
    
    async def export_kvms(self, environment: str) -> List[Dict[str, Any]]:
        """Export KVMs from environment"""
        kvms = []
        try:
            kvm_names = self.client.list_kvms(environment)
            self.logger.info(f"Found {len(kvm_names)} KVMs in {environment}")
            
            for kvm_name in kvm_names:
                try:
                    kvm_data = self.client.get_kvm(environment, kvm_name)
                    kvms.append(kvm_data)
                    self.logger.info(f"Exported KVM: {kvm_name}")
                except Exception as e:
                    self.logger.error(f"Failed to export KVM {kvm_name}: {str(e)}")
        
        except Exception as e:
            self.logger.error(f"Failed to list KVMs: {str(e)}")
        
        return kvms
    
    async def export_api_products(self) -> List[Dict[str, Any]]:
        """Export API products"""
        products = []
        try:
            product_names = self.client.list_api_products()
            self.logger.info(f"Found {len(product_names)} API products to export")
            
            for product_name in product_names:
                try:
                    product_data = self.client.get_api_product(product_name)
                    products.append(product_data)
                    self.logger.info(f"Exported API product: {product_name}")
                except Exception as e:
                    self.logger.error(f"Failed to export API product {product_name}: {str(e)}")
        
        except Exception as e:
            self.logger.error(f"Failed to list API products: {str(e)}")
        
        return products
    
    async def export_developers(self) -> List[Dict[str, Any]]:
        """Export developers"""
        developers = []
        try:
            developer_emails = self.client.list_developers()
            self.logger.info(f"Found {len(developer_emails)} developers to export")
            
            for email in developer_emails:
                try:
                    dev_data = self.client.get_developer(email)
                    developers.append(dev_data)
                    self.logger.info(f"Exported developer: {email}")
                except Exception as e:
                    self.logger.error(f"Failed to export developer {email}: {str(e)}")
        
        except Exception as e:
            self.logger.error(f"Failed to list developers: {str(e)}")
        
        return developers
    
    async def export_developer_apps(self) -> List[Dict[str, Any]]:
        """Export developer apps"""
        apps = []
        try:
            # First get all developers
            developer_emails = self.client.list_developers()
            
            for email in developer_emails:
                try:
                    app_names = self.client.list_developer_apps(email)
                    for app_name in app_names:
                        try:
                            app_data = self.client.get_developer_app(email, app_name)
                            apps.append(app_data)
                            self.logger.info(f"Exported app: {app_name} for {email}")
                        except Exception as e:
                            self.logger.error(f"Failed to export app {app_name}: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Failed to list apps for {email}: {str(e)}")
        
        except Exception as e:
            self.logger.error(f"Failed to export developer apps: {str(e)}")
        
        return apps
    
    def _count_resources(self, export_data: Dict[str, Any]) -> int:
        """Count total resources exported"""
        total = 0
        for key, value in export_data.items():
            if isinstance(value, list):
                total += len(value)
        return total
