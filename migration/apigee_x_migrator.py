import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import requests

# Add the migration directory to the path so we can import resources
sys.path.insert(0, os.path.dirname(__file__))

from resources import MigrateResources

# Base directory = backend/
BASE_DIR = Path(__file__).resolve().parent.parent


class ApigeeXMigrator:
    """
    Wrapper class to integrate user's migration scripts with the FastAPI backend.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize with Apigee X configuration"""
        
        self.config = config
        self.apigeex_mgmt_url = config.get("apigeex_mgmt_url", "https://apigee.googleapis.com/v1/organizations/")
        self.apigeex_org_name = config.get("apigeex_org_name", "")
        self.apigeex_token = config.get("apigeex_token", "")
        self.apigeex_env = config.get("apigeex_env", "eval")

        # Create logs folder at backend/logs
        self.logs_dir = BASE_DIR / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        base_dir = os.path.dirname(os.path.abspath(__file__))  # directory of current script
        
        self.folder_name = BASE_DIR / "data_edge"
        # Create log file
        self.log_file = self.logs_dir / "migration_logs.txt"
        with open(self.log_file, "w+", encoding="utf-8") as f:
            timestamp = datetime.now(timezone.utc)
            f.write(f"TimeStamp {timestamp}\n")

    # -------------------------
    # CREDENTIAL VERIFICATION
    # -------------------------
    def verify_credentials(self) -> tuple[bool, str]:
        try:
            response, status_code = MigrateResources.get_resource(
                "apis",
                self.apigeex_mgmt_url,
                self.apigeex_org_name,
                self.apigeex_token
            )
            if status_code == 200:
                return True, "Authentication successful"
            return False, f"Authentication failed with status {status_code}"
        except Exception as e:
            return False, f"Authentication error: {str(e)}"

    # -------------------------------------------------------
    # ADD resource_exists HERE ↓↓↓
    # -------------------------------------------------------
    def resource_exists(self, resource_type: str, resource_name: str) -> bool:
        base = f"{self.apigeex_mgmt_url.rstrip('/')}/{self.apigeex_org_name}"

        endpoints = {
            "proxy": f"{base}/apis/{resource_name}",
            "sharedflow": f"{base}/sharedflows/{resource_name}",
            "kvm": f"{base}/environments/{self.apigeex_env}/keyvaluemaps/{resource_name}",
            "targetserver": f"{base}/environments/{self.apigeex_env}/targetservers/{resource_name}",
            "developer": f"{base}/developers/{resource_name}",
            "apiproduct": f"{base}/apiproducts/{resource_name}",
        }

        url = endpoints.get(resource_type)
        if not url:
            return False

        headers = {"Authorization": f"Bearer {self.apigeex_token}"}
        r = requests.get(url, headers=headers)

        return r.status_code == 200
    
    def migrate_target_server(self, ts_name: str) -> Dict[str, Any]:
        """
        Migrate a single target server.
        
        Args:
            ts_name: Name of the target server file
            
        Returns:
            Dictionary with migration result
        """
        try:
            if self.resource_exists("targetserver", ts_name.replace(".json", "")):
                return {
                    "resource_type": "targetserver",
                    "resource_name": ts_name,
                    "status_code": 409,
                    "success": False,
                    "message": f"Target Server '{ts_name}' already exists"
                }
            ts_path = os.path.join(self.folder_name, "targetservers", "env", "prod")
            f_path = os.path.join(ts_path, ts_name)
            
            with open(f_path, 'r') as file:
                data = json.load(file)
            
            status_code, response_text = MigrateResources.Target_Servers(
                self.apigeex_mgmt_url,
                self.apigeex_org_name,
                self.apigeex_token,
                data,
                self.apigeex_env
            )
            
            result = {
                "resource_type": "targetserver",
                "resource_name": ts_name,
                "status_code": status_code,
                "success": status_code == 200,
                "message": "Target Server migrated successfully" if status_code == 200 else f"Migration failed: {response_text}"
            }
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "targetserver",
                "resource_name": ts_name,
                "status_code": 500,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def migrate_kvm(self, kvm_name: str, scope: str = "env") -> Dict[str, Any]:
        """
        Migrate a single KVM.
        
        Args:
            kvm_name: Name of the KVM file
            scope: 'env' for environment-level, 'org' for organization-level
            
        Returns:
            Dictionary with migration result
        """
        try:
            kvm_base_name = kvm_name.replace(".json", "")

            if self.resource_exists("kvm", kvm_base_name):
                return {
                    "resource_type": "kvm",
                    "resource_name": kvm_name,
                    "status_code": 409,
                    "success": False,
                    "message": f"KVM '{kvm_name}' already exists"
                }
            if scope == "env":
                kvm_path = os.path.join(self.folder_name, "keyvaluemaps", "env", "prod")
            else:
                kvm_path = os.path.join(self.folder_name, "keyvaluemaps", "org")
            
            f_path = os.path.join(kvm_path, kvm_name)
            
            with open(f_path, 'r') as file:
                data = json.load(file)
                name = data['name']
                encrypted = data['encrypted']
            
            kvm_data = {
                "name": name,
                "encrypted": str(encrypted)
            }
            
            if scope == "env":
                status_code, response_text = MigrateResources.Kvms_Env_Level(
                    self.apigeex_mgmt_url,
                    self.apigeex_org_name,
                    self.apigeex_token,
                    kvm_data,
                    self.apigeex_env
                )
            else:
                status_code, response_text = MigrateResources.Kvms_Org_Level(
                    self.apigeex_mgmt_url,
                    self.apigeex_org_name,
                    self.apigeex_token,
                    kvm_data
                )
            
            result = {
                "resource_type": "kvm",
                "resource_name": kvm_name,
                "status_code": status_code,
                "success": status_code == 201,
                "message": "KVM migrated successfully" if status_code == 201 else f"Migration failed: {response_text}"
            }
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "kvm",
                "resource_name": kvm_name,
                "status_code": 500,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def migrate_developer(self, dev_filename: str) -> Dict[str, Any]:
        """
        Migrate a single developer.
        
        Args:
            dev_filename: Name of the developer file
            
        Returns:
            Dictionary with migration result
        """
        try:
            dev_path = os.path.join(self.folder_name, "developers", dev_filename)
            
            with open(dev_path, 'r') as file:
                data = json.load(file)

            if self.resource_exists("developer", data["email"]):
                return {
                    "resource_type": "developer",
                    "resource_name": dev_filename,
                    "status_code": 409,
                    "success": False,
                    "message": f"Developer '{data['email']}' already exists"
                }
            
            developer_data = {
                "firstName": data.get('firstName', ''),
                "lastName": data.get('lastName', ''),
                "userName": data.get('userName', ''),
                "email": data.get('email', ''),
                "organizationName": data.get('organizationName', self.apigeex_org_name)
            }
            
            status_code, response_text = MigrateResources.Developers(
                self.apigeex_mgmt_url,
                self.apigeex_org_name,
                self.apigeex_token,
                developer_data
            )
            
            result = {
                "resource_type": "developer",
                "resource_name": dev_filename,
                "status_code": status_code,
                "success": status_code == 201,
                "message": "Developer migrated successfully" if status_code == 201 else f"Migration failed: {response_text}"
            }
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "developer",
                "resource_name": dev_filename,
                "status_code": 500,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def migrate_product(self, product_filename: str) -> Dict[str, Any]:
        """
        Migrate a single API product.
        
        Args:
            product_filename: Name of the product file
            
        Returns:
            Dictionary with migration result
        """
        try:
            prod_path = os.path.join(self.folder_name, "apiproducts", product_filename)

            with open(prod_path, 'r') as file:
                data = json.load(file)

            if self.resource_exists("apiproduct", data["name"]):
                return {
                    "resource_type": "apiproduct",
                    "resource_name": product_filename,
                    "status_code": 409,
                    "success": False,
                    "message": f"Product '{data['name']}' already exists"
                }
            # Rewrite product file to remove Edge-specific fields
            MigrateResources.Rewrite_product_file(prod_path)
            
            status_code, response_text = MigrateResources.Migrate_product(
                self.apigeex_mgmt_url,
                self.apigeex_org_name,
                self.apigeex_token,
                data
            )
            
            result = {
                "resource_type": "apiproduct",
                "resource_name": product_filename,
                "status_code": status_code,
                "success": status_code == 201,
                "message": "Product migrated successfully" if status_code == 201 else f"Migration failed: {response_text}"
            }
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "apiproduct",
                "resource_name": product_filename,
                "status_code": 500,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def migrate_app(self, app_filename: str) -> Dict[str, Any]:
        """
        Migrate a single developer app.
        
        Args:
            app_filename: Name of the app file
            
        Returns:
            Dictionary with migration result
        """
        try:
            app_path = os.path.join(self.folder_name, "apps", app_filename)
            
            with open(app_path, 'r') as file:
                data = json.load(file)
            
            app_name = data.get('name', '')
            developer_id = data.get('developerId', '')
            
            # Try to get developer email from the developer file
            dev_dir = os.path.join(self.folder_name, "developers")
            developer_email = None
            
            # Search for developer by ID
            for dev_file in os.listdir(dev_dir):
                dev_path = os.path.join(dev_dir, dev_file)
                with open(dev_path, 'r') as f:
                    dev_data = json.load(f)
                    if dev_data.get('developerId') == developer_id:
                        developer_email = dev_data.get('email')
                        break
            
            if not developer_email:
                return {
                    "resource_type": "app",
                    "resource_name": app_filename,
                    "status_code": 400,
                    "success": False,
                    "message": f"Developer not found for app {app_name}"
                }
            
            # Check if app already exists
            app_check_url = f"{self.apigeex_mgmt_url}{self.apigeex_org_name}/developers/{developer_email}/apps/{app_name}"
            headers = {"Authorization": f"Bearer {self.apigeex_token}"}
            check_response = requests.get(app_check_url, headers=headers)
            
            if check_response.status_code == 200:
                return {
                    "resource_type": "app",
                    "resource_name": app_filename,
                    "status_code": 409,
                    "success": False,
                    "message": f"App '{app_name}' already exists"
                }
            
            # Clean up app data - remove Edge-specific fields
            app_data = {
                "name": data.get('name'),
                "status": data.get('status'),
                "apiProducts": [],
                "callbackUrl": data.get('callbackUrl', ''),
                "attributes": data.get('attributes', [])
            }
            
            # Extract API products from credentials
            credentials = data.get('credentials', [])
            api_products = []
            for cred in credentials:
                for prod in cred.get('apiProducts', []):
                    prod_name = prod.get('apiproduct')
                    if prod_name and prod_name not in api_products:
                        api_products.append(prod_name)
            
            app_data['apiProducts'] = api_products
            
            # Migrate the app
            status_code, response_text = MigrateResources.Migrate_app(
                self.apigeex_mgmt_url,
                self.apigeex_org_name,
                self.apigeex_token,
                developer_email,
                app_data
            )
            
            result = {
                "resource_type": "app",
                "resource_name": app_filename,
                "status_code": status_code,
                "success": status_code == 201,
                "message": "App migrated successfully" if status_code == 201 else f"Migration failed: {response_text}"
            }
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "app",
                "resource_name": app_filename,
                "status_code": 500,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def migrate_proxy(self, proxy_name: str, deploy_after_migration: bool = False) -> Dict[str, Any]:
        """
        Migrate a single API proxy.
        
        Args:
            proxy_name: Name of the proxy (without .zip extension)
            deploy_after_migration: Whether to deploy the proxy after migration
            
        Returns:
            Dictionary with migration result
        """
        try:
            if self.resource_exists("proxy", proxy_name):
                return {
                    "resource_type": "proxy",
                    "resource_name": proxy_name,
                    "status_code": 409,
                    "success": False,
                    "message": f"Proxy '{proxy_name}' already exists"
                }
            proxy_path = os.path.join(self.folder_name, "proxies")
            
            status_code, response_text = MigrateResources.Proxies(
                self.apigeex_mgmt_url,
                self.apigeex_org_name,
                self.apigeex_token,
                proxy_path,
                proxy_name
            )
            
            result = {
                "resource_type": "proxy",
                "resource_name": proxy_name,
                "status_code": status_code,
                "success": status_code == 200,
                "message": "Proxy migrated successfully" if status_code == 200 else f"Migration failed: {response_text}"
            }
            
            # Deploy proxy if migration was successful and deployment is requested
            if result["success"] and deploy_after_migration:
                deployment_result = self.deploy_proxy(proxy_name)
                if deployment_result["success"]:
                    result["message"] += " and deployed successfully"
                    result["deployment_status"] = "deployed"
                else:
                    result["message"] += f" but deployment failed: {deployment_result['message']}"
                    result["deployment_status"] = "failed"
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "proxy",
                "resource_name": proxy_name,
                "status_code": 500,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def migrate_sharedflow(self, sf_name: str, deploy_after_migration: bool = False) -> Dict[str, Any]:
        """
        Migrate a single shared flow.
        
        Args:
            sf_name: Name of the shared flow (without .zip extension)
            deploy_after_migration: Whether to deploy the shared flow after migration
            
        Returns:
            Dictionary with migration result
        """
        try:
            if self.resource_exists("sharedflow", sf_name):
                return {
                    "resource_type": "sharedflow",
                    "resource_name": sf_name,
                    "status_code": 409,
                    "success": False,
                    "message": f"Shared Flow '{sf_name}' already exists"
                }
            sf_path = os.path.join(self.folder_name, "sharedflows")
            
            status_code, response_text = MigrateResources.Shared_Flows(
                self.apigeex_mgmt_url,
                self.apigeex_org_name,
                self.apigeex_token,
                sf_path,
                sf_name
            )
            
            result = {
                "resource_type": "sharedflow",
                "resource_name": sf_name,
                "status_code": status_code,
                "success": status_code == 200,
                "message": "Shared Flow migrated successfully" if status_code == 200 else f"Migration failed: {response_text}"
            }
            
            # Deploy shared flow if migration was successful and deployment is requested
            if result["success"] and deploy_after_migration:
                deployment_result = self.deploy_sharedflow(sf_name)
                if deployment_result["success"]:
                    result["message"] += " and deployed successfully"
                    result["deployment_status"] = "deployed"
                else:
                    result["message"] += f" but deployment failed: {deployment_result['message']}"
                    result["deployment_status"] = "failed"
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "sharedflow",
                "resource_name": sf_name,
                "status_code": 500,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def deploy_proxy(self, proxy_name: str, revision: str = "1") -> Dict[str, Any]:
        """
        Deploy a proxy to the specified environment.
        
        Args:
            proxy_name: Name of the proxy to deploy
            revision: Revision number to deploy (default: "1")
            
        Returns:
            Dictionary with deployment result
        """
        try:
            # First, get the latest revision if not specified
            if revision == "1":
                revision = self._get_latest_revision(proxy_name, "proxy")
            
            url = f"{self.apigeex_mgmt_url}{self.apigeex_org_name}/environments/{self.apigeex_env}/apis/{proxy_name}/revisions/{revision}/deployments"
            
            headers = {
                "Authorization": f"Bearer {self.apigeex_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers)
            
            result = {
                "resource_type": "proxy_deployment",
                "resource_name": f"{proxy_name} (rev {revision})",
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "message": f"Proxy deployed successfully to {self.apigeex_env}" if response.status_code == 200 else f"Deployment failed: {response.text}"
            }
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "proxy_deployment",
                "resource_name": proxy_name,
                "status_code": 500,
                "success": False,
                "message": f"Deployment error: {str(e)}"
            }
    
    def deploy_sharedflow(self, sf_name: str, revision: str = "1") -> Dict[str, Any]:
        """
        Deploy a shared flow to the specified environment.
        
        Args:
            sf_name: Name of the shared flow to deploy
            revision: Revision number to deploy (default: "1")
            
        Returns:
            Dictionary with deployment result
        """
        try:
            # First, get the latest revision if not specified
            if revision == "1":
                revision = self._get_latest_revision(sf_name, "sharedflow")
            
            url = f"{self.apigeex_mgmt_url}{self.apigeex_org_name}/environments/{self.apigeex_env}/sharedflows/{sf_name}/revisions/{revision}/deployments"
            
            headers = {
                "Authorization": f"Bearer {self.apigeex_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers)
            
            result = {
                "resource_type": "sharedflow_deployment",
                "resource_name": f"{sf_name} (rev {revision})",
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "message": f"Shared flow deployed successfully to {self.apigeex_env}" if response.status_code == 200 else f"Deployment failed: {response.text}"
            }
            
            self._log_migration(result)
            return result
            
        except Exception as e:
            return {
                "resource_type": "sharedflow_deployment",
                "resource_name": sf_name,
                "status_code": 500,
                "success": False,
                "message": f"Deployment error: {str(e)}"
            }
    
    def _get_latest_revision(self, resource_name: str, resource_type: str) -> str:
        """
        Get the latest revision number for a proxy or shared flow.
        
        Args:
            resource_name: Name of the resource
            resource_type: 'proxy' or 'sharedflow'
            
        Returns:
            Latest revision number as string
        """
        try:
            if resource_type == "proxy":
                url = f"{self.apigeex_mgmt_url}{self.apigeex_org_name}/apis/{resource_name}/revisions"
            else:  # sharedflow
                url = f"{self.apigeex_mgmt_url}{self.apigeex_org_name}/sharedflows/{resource_name}/revisions"
            
            headers = {"Authorization": f"Bearer {self.apigeex_token}"}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                revisions = response.json()
                return str(max(int(rev) for rev in revisions))
            else:
                return "1"  # Default to revision 1 if unable to get revisions
                
        except Exception:
            return "1"  # Default to revision 1 on any error
    
    def _log_migration(self, result: Dict[str, Any]):
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                line = (
                    f"|| {result['resource_type']} {result['resource_name']} "
                    f"|| {result['status_code']} || {result['message']} ||\n"
                )
                f.write(line)
        except Exception as e:
            print(f"Failed to write log: {e}")

    # ------------------------------------------------------------
    # ADD THIS (Indented properly!)
    # ------------------------------------------------------------
    def migrate_and_deploy_proxy(self, proxy_name: str) -> Dict[str, Any]:
        """
        Migrate and deploy a proxy in one operation.
        
        Args:
            proxy_name: Name of the proxy
            
        Returns:
            Dictionary with migration and deployment result
        """
        return self.migrate_proxy(proxy_name, deploy_after_migration=True)
    
    def migrate_and_deploy_sharedflow(self, sf_name: str) -> Dict[str, Any]:
        """
        Migrate and deploy a shared flow in one operation.
        
        Args:
            sf_name: Name of the shared flow
            
        Returns:
            Dictionary with migration and deployment result
        """
        return self.migrate_sharedflow(sf_name, deploy_after_migration=True)
    
    def migrate_with_retry(self, func, *args, retries: int = 3, delay: float = 1.0):
        """
        Retry wrapper for any migration function.
        """
        import time

        for attempt in range(1, retries + 1):
            result = func(*args)

            if result.get("success"):
                return result

            if attempt == retries:
                result["message"] += f" (failed after {retries} retries)"
                return result

            time.sleep(delay)

    # ------------------------------------------------------------
    # ADD THIS ALSO — MUST be indented inside class!
    # ------------------------------------------------------------
    async def migrate_all(self) -> Dict[str, Any]:
        """
        Runs all migrations in parallel.
        """
        import os
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=10)
        loop = asyncio.get_event_loop()
        tasks = []

        # ---------- Target Servers ----------
        ts_dir = os.path.join(self.folder_name, "targetservers", "env", "prod")
        for f in os.listdir(ts_dir):
            tasks.append(
                loop.run_in_executor(
                    executor,
                    self.migrate_with_retry,
                    self.migrate_target_server,
                    f
                )
            )

        # ---------- KVM (env-level) ----------
        kvm_dir = os.path.join(self.folder_name, "keyvaluemaps", "env", "prod")
        for f in os.listdir(kvm_dir):
            tasks.append(
                loop.run_in_executor(
                    executor,
                    self.migrate_with_retry,
                    self.migrate_kvm,
                    f,
                    "env"
                )
            )

        # ---------- KVM (org-level) ----------
        org_kvm_dir = os.path.join(self.folder_name, "keyvaluemaps", "org")
        for f in os.listdir(org_kvm_dir):
            tasks.append(
                loop.run_in_executor(
                    executor,
                    self.migrate_with_retry,
                    self.migrate_kvm,
                    f,
                    "org"
                )
            )

        # ---------- Developers ----------
        dev_dir = os.path.join(self.folder_name, "developers")
        for f in os.listdir(dev_dir):
            tasks.append(
                loop.run_in_executor(
                    executor,
                    self.migrate_with_retry,
                    self.migrate_developer,
                    f
                )
            )

        # ---------- Apps ----------
        app_dir = os.path.join(self.folder_name, "apps")
        if os.path.exists(app_dir):
            for f in os.listdir(app_dir):
                tasks.append(
                    loop.run_in_executor(
                        executor,
                        self.migrate_with_retry,
                        self.migrate_app,
                        f
                    )
                )

        # ---------- Products ----------
        prod_dir = os.path.join(self.folder_name, "apiproducts")
        for f in os.listdir(prod_dir):
            tasks.append(
                loop.run_in_executor(
                    executor,
                    self.migrate_with_retry,
                    self.migrate_product,
                    f
                )
            )

        # ---------- Proxies ----------
        proxy_dir = os.path.join(self.folder_name, "proxies")
        for f in os.listdir(proxy_dir):
            proxy_name = f.replace(".zip", "")
            tasks.append(
                loop.run_in_executor(
                    executor,
                    self.migrate_with_retry,
                    self.migrate_proxy,
                    proxy_name
                )
            )

        # ---------- Sharedflows ----------
        sf_dir = os.path.join(self.folder_name, "sharedflows")
        for f in os.listdir(sf_dir):
            sf_name = f.replace(".zip", "")
            tasks.append(
                loop.run_in_executor(
                    executor,
                    self.migrate_with_retry,
                    self.migrate_sharedflow,
                    sf_name
                )
            )

        results = await asyncio.gather(*tasks)

        return {
            "summary": {
                "total": len(results),
                "success": sum(1 for r in results if r["success"]),
                "failed": sum(1 for r in results if not r["success"]),
            },
            "details": results
        }
