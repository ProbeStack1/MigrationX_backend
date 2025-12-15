"""GCS-based assessment service for V2 /assess endpoint"""
import json
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import io

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    storage = None

from migration.assessment_engine import MigrationAssessment
from migration.dependency_analyzer import DependencyAnalyzer
from utils.firestore_logger import log_info, log_error, log_success, generate_operation_id

logger = logging.getLogger(__name__)


class GCSAssessmentService:
    """Service for performing assessment with data from Google Cloud Storage"""
    
    def __init__(self, bucket_name: str, gcs_prefix: str = "", firestore_client=None):
        """
        Initialize GCS Assessment Service
        
        Args:
            bucket_name: GCS bucket name containing assessment data
            gcs_prefix: Optional prefix path in GCS bucket (e.g., "apigee-edge-data/")
            firestore_client: Firestore client instance for persisting results
        """
        if not GCS_AVAILABLE:
            raise ImportError("google-cloud-storage is not installed. Install it with: pip install google-cloud-storage")
        
        self.bucket_name = bucket_name
        self.gcs_prefix = gcs_prefix.rstrip("/") + "/" if gcs_prefix else ""
        self.firestore_client = firestore_client
        self.operation_id = generate_operation_id()
        self.gcs_failures_count = 0  # Track number of GCS read failures
        
        # Initialize GCS client
        try:
            self.storage_client = storage.Client()
            self.bucket = self.storage_client.bucket(bucket_name)
            logger.info(f"Initialized GCS client for bucket: {bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {str(e)}")
            raise
    
    def run_assessment(self) -> Dict[str, Any]:
        """
        Run complete assessment workflow:
        1. Fetch data from GCS
        2. Execute assessment
        3. Write results to Firestore
        4. Return results
        
        Returns:
            Assessment results dictionary
        """
        log_info("=" * 80, self.operation_id, "ASSESSMENT", "V2")
        log_info("🚀 Starting V2 assessment workflow", self.operation_id, "ASSESSMENT", "V2",
                metadata={"operation_id": self.operation_id, "bucket": self.bucket_name, "prefix": self.gcs_prefix})
        
        try:
            # Step 1: Fetch data from GCS
            log_info("Step 1: Fetching assessment data from GCS (non-blocking mode)", self.operation_id, "ASSESSMENT", "V2",
                    metadata={"bucket": self.bucket_name, "prefix": self.gcs_prefix})
            edge_data = self._fetch_data_from_gcs()
            
            # Log results including any failures
            failure_info = f" ({self.gcs_failures_count} GCS read failures logged)" if self.gcs_failures_count > 0 else ""
            log_success(f"Data fetch completed from GCS: {len(edge_data.get('proxies', []))} proxies, "
                       f"{len(edge_data.get('shared_flows', []))} shared flows{failure_info}", 
                       self.operation_id, "ASSESSMENT", "V2",
                       metadata={
                           "proxies": len(edge_data.get("proxies", [])),
                           "shared_flows": len(edge_data.get("shared_flows", [])),
                           "target_servers": len(edge_data.get("target_servers", [])),
                           "kvms": len(edge_data.get("kvms", [])),
                           "api_products": len(edge_data.get("api_products", [])),
                           "apps": len(edge_data.get("apps", [])),
                           "developers": len(edge_data.get("developers", [])),
                           "gcs_failures_count": self.gcs_failures_count
                       })
            
            # Step 2: Execute assessment
            log_info("Step 2: Executing migration assessment", self.operation_id, "ASSESSMENT", "V2")
            assessment = self._execute_assessment(edge_data)
            log_success("Assessment execution completed", self.operation_id, "ASSESSMENT", "V2",
                       metadata={"overall_status": assessment.get("overall_status"),
                                "total_issues": assessment.get("total_issues", 0),
                                "total_warnings": assessment.get("total_warnings", 0)})
            
            # Step 3: Write to Firestore
            if self.firestore_client:
                log_info("Step 3: Persisting assessment results to Firestore", self.operation_id, "ASSESSMENT", "V2")
                self._write_to_firestore(assessment)
                log_success("Assessment results persisted to Firestore", self.operation_id, "ASSESSMENT", "V2")
            else:
                log_info("Step 3: Skipping Firestore write (client not available)", self.operation_id, "ASSESSMENT", "V2")
            
            log_info("=" * 80, self.operation_id, "ASSESSMENT", "V2")
            
            # Return response structure matching V1 endpoint format
            return {
                "success": True,
                "assessment": assessment
            }
            
        except Exception as e:
            log_error(f"Assessment workflow failed: {str(e)}", self.operation_id, "ASSESSMENT", "V2",
                      metadata={"error": str(e), "error_type": type(e).__name__})
            logger.exception(e)
            raise
    
    def _fetch_data_from_gcs(self) -> Dict[str, Any]:
        """Fetch and parse Edge data from GCS bucket (non-blocking - continues on failures)"""
        # Create a temporary directory to store downloaded files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Download and parse each resource type (each call is non-blocking)
            edge_data = {
                "proxies": self._fetch_proxies_from_gcs(temp_path),
                "shared_flows": self._fetch_shared_flows_from_gcs(temp_path),
                "developers": self._fetch_developers_from_gcs(),
                "apps": self._fetch_apps_from_gcs(),
                "api_products": self._fetch_api_products_from_gcs(),
                "target_servers": self._fetch_target_servers_from_gcs(),
                "kvms": self._fetch_kvms_from_gcs()
            }
            
            return edge_data
    
    def _fetch_proxies_from_gcs(self, temp_path: Path) -> List[Dict[str, Any]]:
        """Fetch and parse proxies from GCS (non-blocking - continues on individual failures)"""
        proxies = []
        proxies_prefix = f"{self.gcs_prefix}proxies/"
        
        try:
            blobs = list(self.bucket.list_blobs(prefix=proxies_prefix))
            zip_blobs = [b for b in blobs if b.name.endswith('.zip')]
        except Exception as e:
            self._log_gcs_failure(
                resource_type="proxies",
                operation="list_blobs",
                gcs_path=proxies_prefix,
                error=str(e),
                error_type=type(e).__name__
            )
            return []
        
        for blob in zip_blobs:
            try:
                proxy_name = Path(blob.name).stem
                proxy_data = {
                    "name": proxy_name,
                    "type": "API Proxy",
                    "policies": [],
                    "targets": [],
                    "endpoints": []
                }
                
                # Download zip to temp location
                zip_path = temp_path / f"{proxy_name}.zip"
                blob.download_to_filename(str(zip_path))
                
                # Extract and parse
                extract_dir = temp_path / proxy_name
                extract_dir.mkdir(exist_ok=True)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Parse policies
                policies_dir = extract_dir / "apiproxy" / "policies"
                if policies_dir.exists():
                    for policy_file in policies_dir.glob("*.xml"):
                        try:
                            with open(policy_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                                policy_data = self._parse_policy_xml(content)
                                if policy_data:
                                    proxy_data["policies"].append(policy_data)
                        except Exception as e:
                            logger.warning(f"Failed to parse policy {policy_file}: {e}")
                
                # Parse targets
                targets_dir = extract_dir / "apiproxy" / "targets"
                if targets_dir.exists():
                    for target_file in targets_dir.glob("*.xml"):
                        proxy_data["targets"].append(target_file.stem)
                
                # Parse endpoints
                endpoints_dir = extract_dir / "apiproxy" / "proxies"
                if endpoints_dir.exists():
                    for endpoint_file in endpoints_dir.glob("*.xml"):
                        proxy_data["endpoints"].append(endpoint_file.stem)
                
                proxy_data["policy_count"] = len(proxy_data["policies"])
                proxies.append(proxy_data)
                
            except Exception as e:
                self._log_gcs_failure(
                    resource_type="proxy",
                    operation="download_and_parse",
                    gcs_path=blob.name,
                    resource_name=Path(blob.name).stem,
                    error=str(e),
                    error_type=type(e).__name__,
                    blob_size=blob.size if hasattr(blob, 'size') else None,
                    blob_updated=blob.updated.isoformat() if hasattr(blob, 'updated') and blob.updated else None
                )
                # Continue processing other proxies
                continue
        
        return proxies
    
    def _fetch_shared_flows_from_gcs(self, temp_path: Path) -> List[Dict[str, Any]]:
        """Fetch and parse shared flows from GCS (non-blocking - continues on individual failures)"""
        flows = []
        flows_prefix = f"{self.gcs_prefix}sharedflows/"
        
        try:
            blobs = list(self.bucket.list_blobs(prefix=flows_prefix))
            zip_blobs = [b for b in blobs if b.name.endswith('.zip')]
        except Exception as e:
            self._log_gcs_failure(
                resource_type="shared_flows",
                operation="list_blobs",
                gcs_path=flows_prefix,
                error=str(e),
                error_type=type(e).__name__
            )
            return []
        
        for blob in zip_blobs:
            try:
                flow_name = Path(blob.name).stem
                flow_data = {
                    "name": flow_name,
                    "type": "Shared Flow",
                    "policies": []
                }
                
                # Download and extract
                zip_path = temp_path / f"{flow_name}.zip"
                blob.download_to_filename(str(zip_path))
                
                extract_dir = temp_path / flow_name
                extract_dir.mkdir(exist_ok=True)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Parse policies
                policies_dir = extract_dir / "sharedflowbundle" / "policies"
                if policies_dir.exists():
                    for policy_file in policies_dir.glob("*.xml"):
                        try:
                            with open(policy_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                                policy_data = self._parse_policy_xml(content)
                                if policy_data:
                                    flow_data["policies"].append(policy_data)
                        except Exception as e:
                            logger.warning(f"Failed to parse policy {policy_file}: {e}")
                
                flow_data["policy_count"] = len(flow_data["policies"])
                flows.append(flow_data)
                
            except Exception as e:
                self._log_gcs_failure(
                    resource_type="shared_flow",
                    operation="download_and_parse",
                    gcs_path=blob.name,
                    resource_name=Path(blob.name).stem,
                    error=str(e),
                    error_type=type(e).__name__,
                    blob_size=blob.size if hasattr(blob, 'size') else None,
                    blob_updated=blob.updated.isoformat() if hasattr(blob, 'updated') and blob.updated else None
                )
                # Continue processing other shared flows
                continue
        
        return flows
    
    def _fetch_developers_from_gcs(self) -> List[Dict[str, Any]]:
        """Fetch and parse developers from GCS (non-blocking - continues on individual failures)"""
        developers = []
        devs_prefix = f"{self.gcs_prefix}developers/"
        
        try:
            blobs = list(self.bucket.list_blobs(prefix=devs_prefix))
        except Exception as e:
            self._log_gcs_failure(
                resource_type="developers",
                operation="list_blobs",
                gcs_path=devs_prefix,
                error=str(e),
                error_type=type(e).__name__
            )
            return []
        
        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue
            
            try:
                content = blob.download_as_text()
                dev_data = json.loads(content)
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
                self._log_gcs_failure(
                    resource_type="developer",
                    operation="download_and_parse",
                    gcs_path=blob.name,
                    resource_name=Path(blob.name).stem,
                    error=str(e),
                    error_type=type(e).__name__,
                    blob_size=blob.size if hasattr(blob, 'size') else None,
                    blob_updated=blob.updated.isoformat() if hasattr(blob, 'updated') and blob.updated else None,
                    additional_context={"content_type": blob.content_type if hasattr(blob, 'content_type') else None}
                )
                # Continue processing other developers
                continue
        
        return developers
    
    def _fetch_apps_from_gcs(self) -> List[Dict[str, Any]]:
        """Fetch and parse apps from GCS (non-blocking - continues on individual failures)"""
        apps = []
        apps_prefix = f"{self.gcs_prefix}apps/"
        
        try:
            blobs = list(self.bucket.list_blobs(prefix=apps_prefix))
        except Exception as e:
            self._log_gcs_failure(
                resource_type="apps",
                operation="list_blobs",
                gcs_path=apps_prefix,
                error=str(e),
                error_type=type(e).__name__
            )
            return []
        
        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue
            
            try:
                content = blob.download_as_text()
                app_data = json.loads(content)
                
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
                self._log_gcs_failure(
                    resource_type="app",
                    operation="download_and_parse",
                    gcs_path=blob.name,
                    resource_name=Path(blob.name).stem,
                    error=str(e),
                    error_type=type(e).__name__,
                    blob_size=blob.size if hasattr(blob, 'size') else None,
                    blob_updated=blob.updated.isoformat() if hasattr(blob, 'updated') and blob.updated else None,
                    additional_context={"content_type": blob.content_type if hasattr(blob, 'content_type') else None}
                )
                # Continue processing other apps
                continue
        
        return apps
    
    def _fetch_api_products_from_gcs(self) -> List[Dict[str, Any]]:
        """Fetch and parse API products from GCS (non-blocking - continues on individual failures)"""
        products = []
        products_prefix = f"{self.gcs_prefix}apiproducts/"
        
        try:
            blobs = list(self.bucket.list_blobs(prefix=products_prefix))
        except Exception as e:
            self._log_gcs_failure(
                resource_type="api_products",
                operation="list_blobs",
                gcs_path=products_prefix,
                error=str(e),
                error_type=type(e).__name__
            )
            return []
        
        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue
            
            try:
                content = blob.download_as_text()
                prod_data = json.loads(content)
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
                self._log_gcs_failure(
                    resource_type="api_product",
                    operation="download_and_parse",
                    gcs_path=blob.name,
                    resource_name=Path(blob.name).stem,
                    error=str(e),
                    error_type=type(e).__name__,
                    blob_size=blob.size if hasattr(blob, 'size') else None,
                    blob_updated=blob.updated.isoformat() if hasattr(blob, 'updated') and blob.updated else None,
                    additional_context={"content_type": blob.content_type if hasattr(blob, 'content_type') else None}
                )
                # Continue processing other products
                continue
        
        return products
    
    def _fetch_target_servers_from_gcs(self) -> List[Dict[str, Any]]:
        """Fetch and parse target servers from GCS (non-blocking - continues on individual failures)"""
        servers = []
        servers_prefix = f"{self.gcs_prefix}targetservers/env/"
        
        try:
            blobs = list(self.bucket.list_blobs(prefix=servers_prefix))
        except Exception as e:
            self._log_gcs_failure(
                resource_type="target_servers",
                operation="list_blobs",
                gcs_path=servers_prefix,
                error=str(e),
                error_type=type(e).__name__
            )
            return []
        
        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue
            
            try:
                # Extract environment from path: targetservers/env/{env}/{file}
                path_parts = blob.name.split('/')
                if len(path_parts) >= 3:
                    environment = path_parts[-2]  # Environment is second to last
                else:
                    environment = "unknown"
                
                content = blob.download_as_text()
                server_data = json.loads(content)
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
                # Extract environment for logging
                path_parts = blob.name.split('/')
                environment = path_parts[-2] if len(path_parts) >= 3 else "unknown"
                
                self._log_gcs_failure(
                    resource_type="target_server",
                    operation="download_and_parse",
                    gcs_path=blob.name,
                    resource_name=Path(blob.name).stem,
                    error=str(e),
                    error_type=type(e).__name__,
                    blob_size=blob.size if hasattr(blob, 'size') else None,
                    blob_updated=blob.updated.isoformat() if hasattr(blob, 'updated') and blob.updated else None,
                    additional_context={
                        "environment": environment,
                        "content_type": blob.content_type if hasattr(blob, 'content_type') else None
                    }
                )
                # Continue processing other target servers
                continue
        
        return servers
    
    def _fetch_kvms_from_gcs(self) -> List[Dict[str, Any]]:
        """Fetch and parse KVMs from GCS (non-blocking - continues on individual failures)"""
        kvms = []
        kvms_prefix = f"{self.gcs_prefix}keyvaluemaps/env/"
        
        try:
            blobs = list(self.bucket.list_blobs(prefix=kvms_prefix))
        except Exception as e:
            self._log_gcs_failure(
                resource_type="kvms",
                operation="list_blobs",
                gcs_path=kvms_prefix,
                error=str(e),
                error_type=type(e).__name__
            )
            return []
        
        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue
            
            try:
                # Extract environment from path: keyvaluemaps/env/{env}/{file}
                path_parts = blob.name.split('/')
                if len(path_parts) >= 3:
                    environment = path_parts[-2]
                else:
                    environment = "unknown"
                
                content = blob.download_as_text()
                kvm_data = json.loads(content)
                kvms.append({
                    "name": kvm_data.get("name"),
                    "environment": environment,
                    "encrypted": kvm_data.get("encrypted", False),
                    "entries": len(kvm_data.get("entry", []))
                })
            except Exception as e:
                # Extract environment for logging
                path_parts = blob.name.split('/')
                environment = path_parts[-2] if len(path_parts) >= 3 else "unknown"
                
                self._log_gcs_failure(
                    resource_type="kvm",
                    operation="download_and_parse",
                    gcs_path=blob.name,
                    resource_name=Path(blob.name).stem,
                    error=str(e),
                    error_type=type(e).__name__,
                    blob_size=blob.size if hasattr(blob, 'size') else None,
                    blob_updated=blob.updated.isoformat() if hasattr(blob, 'updated') and blob.updated else None,
                    additional_context={
                        "environment": environment,
                        "content_type": blob.content_type if hasattr(blob, 'content_type') else None
                    }
                )
                # Continue processing other KVMs
                continue
        
        return kvms
    
    def _log_gcs_failure(
        self,
        resource_type: str,
        operation: str,
        gcs_path: str,
        error: str,
        error_type: str,
        resource_name: Optional[str] = None,
        blob_size: Optional[int] = None,
        blob_updated: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log GCS read failure to Firestore collection 'gcs_read_failures'
        
        Args:
            resource_type: Type of resource (e.g., 'proxy', 'developer', 'app')
            operation: Operation that failed (e.g., 'list_blobs', 'download_and_parse')
            gcs_path: Full GCS path to the resource
            error: Error message
            error_type: Type of exception
            resource_name: Name of the specific resource (if applicable)
            blob_size: Size of the blob in bytes (if available)
            blob_updated: Last updated timestamp of blob (if available)
            additional_context: Additional contextual information
        """
        # Always increment failure counter for tracking
        self.gcs_failures_count += 1
        
        try:
            if not self.firestore_client:
                # If Firestore not available, just log to console
                logger.error(
                    f"GCS read failure - Resource: {resource_type}, Operation: {operation}, "
                    f"Path: {gcs_path}, Error: {error}"
                )
                return
            
            # Create failure document
            failure_doc = {
                "operation_id": self.operation_id,
                "timestamp": datetime.now(timezone.utc),
                "bucket_name": self.bucket_name,
                "gcs_prefix": self.gcs_prefix,
                "resource_type": resource_type,
                "operation": operation,
                "gcs_path": gcs_path,
                "resource_name": resource_name,
                "error": error,
                "error_type": error_type,
                "blob_size": blob_size,
                "blob_updated": blob_updated,
                "additional_context": additional_context or {}
            }
            
            # Write to Firestore collection 'gcs_read_failures'
            collection_ref = self.firestore_client.collection('gcs_read_failures')
            # Use auto-generated document ID for uniqueness
            collection_ref.add(failure_doc)
            
            logger.warning(
                f"GCS read failure logged to Firestore - Resource: {resource_type}, "
                f"Path: {gcs_path}, Error: {error}"
            )
            
        except Exception as e:
            # Don't fail the operation if Firestore logging fails
            logger.error(
                f"Failed to log GCS failure to Firestore: {str(e)}. "
                f"Original failure - Resource: {resource_type}, Path: {gcs_path}, Error: {error}"
            )
    
    def _parse_policy_xml(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse policy XML content to extract policy type"""
        try:
            import re
            # Find the first XML tag that's not the XML declaration
            match = re.search(r'<([a-zA-Z][a-zA-Z0-9_-]*)', content)
            if match:
                policy_type = match.group(1)
                # Try to extract name from content
                name_match = re.search(r'name=["\']([^"\']+)["\']', content)
                policy_name = name_match.group(1) if name_match else "unknown"
                return {
                    "name": policy_name,
                    "type": policy_type
                }
            return None
        except Exception as e:
            logger.warning(f"Failed to parse policy XML: {e}")
            return None
    
    def _execute_assessment(self, edge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute migration assessment using existing assessment engine"""
        try:
            # Perform assessment
            assessor = MigrationAssessment()
            assessment = assessor.assess_all_resources(edge_data)
            
            # Add dependency analysis
            dep_analyzer = DependencyAnalyzer()
            dependencies = dep_analyzer.analyze_dependencies(edge_data)
            assessment["dependencies"] = dependencies
            assessment["migration_order"] = dep_analyzer.get_migration_order(dependencies)
            
            return assessment
            
        except Exception as e:
            logger.error(f"Assessment execution failed: {str(e)}")
            raise RuntimeError(f"Assessment execution failed: {str(e)}") from e
    
    def _write_to_firestore(self, assessment: Dict[str, Any]) -> None:
        """Write assessment results to Firestore collection"""
        if not self.firestore_client:
            raise RuntimeError("Firestore client not available")
        
        try:
            collection_ref = self.firestore_client.collection('assessment_apigee_results')
            
            # Create document with assessment results
            # Include metadata for V2-specific information (not returned in response, but stored in Firestore)
            doc_data = {
                "operation_id": self.operation_id,
                "timestamp": datetime.now(timezone.utc),
                "bucket": self.bucket_name,
                "gcs_prefix": self.gcs_prefix,
                "assessment": assessment,
                "gcs_failures_count": self.gcs_failures_count,
                "summary": {
                    "overall_status": assessment.get("overall_status"),
                    "total_issues": assessment.get("total_issues", 0),
                    "total_warnings": assessment.get("total_warnings", 0),
                    "proxies_count": len(assessment.get("proxy_assessments", [])),
                    "shared_flows_count": len(assessment.get("shared_flow_assessments", [])),
                    "target_servers_count": len(assessment.get("target_server_assessments", [])),
                    "kvms_count": len(assessment.get("kvm_assessments", [])),
                    "api_products_count": len(assessment.get("api_product_assessments", [])),
                    "apps_count": len(assessment.get("app_assessments", [])),
                    "developers_count": len(assessment.get("developer_assessments", []))
                }
            }
            
            # Use operation_id as document ID for traceability
            doc_ref = collection_ref.document(self.operation_id)
            doc_ref.set(doc_data)
            
            logger.info(f"Assessment results written to Firestore with document ID: {self.operation_id}")
            
        except Exception as e:
            logger.error(f"Failed to write assessment results to Firestore: {str(e)}")
            raise RuntimeError(f"Firestore write failed: {str(e)}") from e

