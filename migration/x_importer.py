"""Import transformed resources into Apigee X"""
import asyncio
from typing import Dict, Any, List
import logging
from clients.apigee_x_client import ApigeeXClient
from utils.logger import MigrationLogger

logger = logging.getLogger(__name__)


class ApigeeXImporter:
    """Import resources into Apigee X organization"""
    
    def __init__(self, x_client: ApigeeXClient, migration_logger: MigrationLogger, dry_run: bool = False):
        self.client = x_client
        self.logger = migration_logger
        self.dry_run = dry_run
        self.import_stats = {
            "proxies_imported": 0,
            "shared_flows_imported": 0,
            "target_servers_created": 0,
            "kvms_created": 0,
            "api_products_created": 0,
            "developers_created": 0,
            "apps_created": 0,
        }
    
    async def import_all(self, x_data: Dict[str, Any], environment: str) -> Dict[str, Any]:
        """Import all transformed resources into Apigee X"""
        if self.dry_run:
            self.logger.info("DRY RUN MODE - No actual imports will be performed")
        
        self.logger.info(f"Starting import to Apigee X org: {self.client.organization}, env: {environment}")
        
        results = {
            "success": True,
            "imported": [],
            "failed": [],
            "skipped": []
        }
        
        try:
            # Import in dependency order
            
            # 1. Target servers (needed by proxies)
            self.logger.info("Importing target servers...")
            await self.import_target_servers(x_data.get("target_servers", []), environment, results)
            
            # 2. KVMs
            self.logger.info("Importing KVMs...")
            await self.import_kvms(x_data.get("kvms", []), environment, results)
            
            # 3. Shared flows (needed by proxies)
            self.logger.info("Importing shared flows...")
            await self.import_shared_flows(x_data.get("shared_flows", []), environment, results)
            
            # 4. API proxies
            self.logger.info("Importing API proxies...")
            await self.import_proxies(x_data.get("proxies", []), environment, results)
            
            # 5. API products
            self.logger.info("Importing API products...")
            await self.import_api_products(x_data.get("api_products", []), results)
            
            # 6. Developers
            self.logger.info("Importing developers...")
            await self.import_developers(x_data.get("developers", []), results)
            
            # 7. Developer apps
            self.logger.info("Importing developer apps...")
            await self.import_developer_apps(x_data.get("developer_apps", []), results)
            
            self.logger.success(f"Import completed. Stats: {self.import_stats}")
            
        except Exception as e:
            self.logger.error(f"Import failed: {str(e)}")
            results["success"] = False
            raise
        
        return results
    
    async def import_proxies(self, proxies: List[Dict[str, Any]], environment: str, results: Dict[str, Any]):
        """Import API proxies"""
        for proxy in proxies:
            proxy_name = proxy.get("name", "unknown")
            
            try:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would import proxy: {proxy_name}")
                    results["skipped"].append({"type": "proxy", "name": proxy_name, "reason": "dry_run"})
                else:
                    # Import proxy bundle
                    bundle_data = b"mock-bundle-data"  # In real mode, read actual bundle
                    import_result = self.client.import_proxy(proxy_name, bundle_data)
                    
                    # Deploy to environment
                    revision = import_result.get("revision", "1")
                    deploy_result = self.client.deploy_proxy(proxy_name, revision, environment)
                    
                    self.logger.success(f"Imported and deployed proxy: {proxy_name}")
                    results["imported"].append({"type": "proxy", "name": proxy_name})
                    self.import_stats["proxies_imported"] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to import proxy {proxy_name}: {str(e)}")
                results["failed"].append({"type": "proxy", "name": proxy_name, "error": str(e)})
    
    async def import_shared_flows(self, flows: List[Dict[str, Any]], environment: str, results: Dict[str, Any]):
        """Import shared flows"""
        for flow in flows:
            flow_name = flow.get("name", "unknown")
            
            try:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would import shared flow: {flow_name}")
                    results["skipped"].append({"type": "shared_flow", "name": flow_name, "reason": "dry_run"})
                else:
                    bundle_data = b"mock-flow-bundle"
                    import_result = self.client.import_shared_flow(flow_name, bundle_data)
                    
                    revision = import_result.get("revision", "1")
                    self.client.deploy_shared_flow(flow_name, revision, environment)
                    
                    self.logger.success(f"Imported shared flow: {flow_name}")
                    results["imported"].append({"type": "shared_flow", "name": flow_name})
                    self.import_stats["shared_flows_imported"] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to import shared flow {flow_name}: {str(e)}")
                results["failed"].append({"type": "shared_flow", "name": flow_name, "error": str(e)})
    
    async def import_target_servers(self, servers: List[Dict[str, Any]], environment: str, results: Dict[str, Any]):
        """Import target servers"""
        for server in servers:
            server_name = server.get("name", "unknown")
            
            try:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would create target server: {server_name}")
                    results["skipped"].append({"type": "target_server", "name": server_name, "reason": "dry_run"})
                else:
                    self.client.create_target_server(environment, server)
                    self.logger.success(f"Created target server: {server_name}")
                    results["imported"].append({"type": "target_server", "name": server_name})
                    self.import_stats["target_servers_created"] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to create target server {server_name}: {str(e)}")
                results["failed"].append({"type": "target_server", "name": server_name, "error": str(e)})
    
    async def import_kvms(self, kvms: List[Dict[str, Any]], environment: str, results: Dict[str, Any]):
        """Import KVMs"""
        for kvm in kvms:
            kvm_name = kvm.get("name", "unknown")
            
            try:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would create KVM: {kvm_name}")
                    results["skipped"].append({"type": "kvm", "name": kvm_name, "reason": "dry_run"})
                else:
                    self.client.create_kvm(environment, kvm)
                    self.logger.success(f"Created KVM: {kvm_name}")
                    results["imported"].append({"type": "kvm", "name": kvm_name})
                    self.import_stats["kvms_created"] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to create KVM {kvm_name}: {str(e)}")
                results["failed"].append({"type": "kvm", "name": kvm_name, "error": str(e)})
    
    async def import_api_products(self, products: List[Dict[str, Any]], results: Dict[str, Any]):
        """Import API products"""
        for product in products:
            product_name = product.get("name", "unknown")
            
            try:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would create API product: {product_name}")
                    results["skipped"].append({"type": "api_product", "name": product_name, "reason": "dry_run"})
                else:
                    self.client.create_api_product(product)
                    self.logger.success(f"Created API product: {product_name}")
                    results["imported"].append({"type": "api_product", "name": product_name})
                    self.import_stats["api_products_created"] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to create API product {product_name}: {str(e)}")
                results["failed"].append({"type": "api_product", "name": product_name, "error": str(e)})
    
    async def import_developers(self, developers: List[Dict[str, Any]], results: Dict[str, Any]):
        """Import developers"""
        for developer in developers:
            dev_email = developer.get("email", "unknown")
            
            try:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would create developer: {dev_email}")
                    results["skipped"].append({"type": "developer", "name": dev_email, "reason": "dry_run"})
                else:
                    self.client.create_developer(developer)
                    self.logger.success(f"Created developer: {dev_email}")
                    results["imported"].append({"type": "developer", "name": dev_email})
                    self.import_stats["developers_created"] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to create developer {dev_email}: {str(e)}")
                results["failed"].append({"type": "developer", "name": dev_email, "error": str(e)})
    
    async def import_developer_apps(self, apps: List[Dict[str, Any]], results: Dict[str, Any]):
        """Import developer apps"""
        for app in apps:
            app_name = app.get("name", "unknown")
            developer_email = app.get("developer_email", "")
            
            try:
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would create app: {app_name}")
                    results["skipped"].append({"type": "app", "name": app_name, "reason": "dry_run"})
                else:
                    self.client.create_developer_app(developer_email, app)
                    self.logger.success(f"Created app: {app_name} for {developer_email}")
                    results["imported"].append({"type": "app", "name": app_name})
                    self.import_stats["apps_created"] += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to create app {app_name}: {str(e)}")
                results["failed"].append({"type": "app", "name": app_name, "error": str(e)})
    
    def get_import_stats(self) -> Dict[str, Any]:
        """Get import statistics"""
        return self.import_stats
