"""Validate migration results"""
from typing import Dict, Any, List
import logging
from clients.edge_client import EdgeClient
from clients.apigee_x_client import ApigeeXClient
from utils.logger import MigrationLogger
from utils.diff_calculator import DiffCalculator
from models.migration_models import ValidationReport

logger = logging.getLogger(__name__)


class MigrationValidator:
    """Validate that migration was successful"""
    
    def __init__(self, edge_client: EdgeClient, x_client: ApigeeXClient, migration_logger: MigrationLogger):
        self.edge_client = edge_client
        self.x_client = x_client
        self.logger = migration_logger
        self.diff_calculator = DiffCalculator()
    
    async def validate_migration(self, edge_data: Dict[str, Any], x_data: Dict[str, Any], 
                                  environment: str, job_id: str) -> ValidationReport:
        """Validate complete migration"""
        self.logger.info("Starting migration validation...")
        
        report = ValidationReport(
            migration_job_id=job_id,
            status="passed"
        )
        
        try:
            # Validate proxies
            self.logger.info("Validating API proxies...")
            report.proxy_validations = await self.validate_proxies(
                edge_data.get("proxies", []),
                x_data.get("proxies", [])
            )
            
            # Validate target servers
            self.logger.info("Validating target servers...")
            report.target_server_validations = await self.validate_target_servers(
                edge_data.get("target_servers", []),
                x_data.get("target_servers", [])
            )
            
            # Validate KVMs
            self.logger.info("Validating KVMs...")
            report.kvm_validations = await self.validate_kvms(
                edge_data.get("kvms", []),
                x_data.get("kvms", [])
            )
            
            # Validate API products
            self.logger.info("Validating API products...")
            report.api_product_validations = await self.validate_api_products(
                edge_data.get("api_products", []),
                x_data.get("api_products", [])
            )
            
            # Validate developers
            self.logger.info("Validating developers...")
            report.developer_validations = await self.validate_developers(
                edge_data.get("developers", []),
                x_data.get("developers", [])
            )
            
            # Calculate totals
            report.total_checks = self._count_total_checks(report)
            report.passed_checks = self._count_passed_checks(report)
            report.failed_checks = self._count_failed_checks(report)
            report.warning_checks = self._count_warning_checks(report)
            
            # Determine overall status
            if report.failed_checks > 0:
                report.status = "failed"
            elif report.warning_checks > 0:
                report.status = "warnings"
            else:
                report.status = "passed"
            
            report.summary = self._generate_summary(report)
            self.logger.success(f"Validation completed: {report.status}")
            
        except Exception as e:
            self.logger.error(f"Validation failed: {str(e)}")
            report.status = "failed"
            report.summary = f"Validation error: {str(e)}"
        
        return report
    
    async def validate_proxies(self, edge_proxies: List[Dict[str, Any]], 
                                x_proxies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate proxy migration"""
        validations = []
        
        edge_proxy_map = {p.get("name"): p for p in edge_proxies}
        x_proxy_map = {p.get("name"): p for p in x_proxies}
        
        for proxy_name in edge_proxy_map.keys():
            validation = {
                "resource_name": proxy_name,
                "status": "passed",
                "checks": [],
                "warnings": [],
                "errors": []
            }
            
            # Check if proxy exists in X
            if proxy_name not in x_proxy_map:
                validation["status"] = "failed"
                validation["errors"].append(f"Proxy '{proxy_name}' not found in Apigee X")
                validations.append(validation)
                continue
            
            edge_proxy = edge_proxy_map[proxy_name]
            x_proxy = x_proxy_map[proxy_name]
            
            # Check base paths
            if edge_proxy.get("base_paths") != x_proxy.get("base_paths"):
                validation["warnings"].append("Base paths differ between Edge and X")
            
            # Check policies
            edge_policies = edge_proxy.get("policies", [])
            x_policies = x_proxy.get("policies", [])
            
            if len(edge_policies) != len(x_policies):
                validation["warnings"].append(
                    f"Policy count differs: Edge={len(edge_policies)}, X={len(x_policies)}"
                )
            
            # Check for removed policies
            edge_policy_names = {p.get("name") for p in edge_policies}
            x_policy_names = {p.get("name") for p in x_policies}
            removed_policies = edge_policy_names - x_policy_names
            
            if removed_policies:
                validation["warnings"].append(
                    f"Policies removed during transformation: {', '.join(removed_policies)}"
                )
            
            validation["checks"].append({"check": "Proxy exists in X", "passed": True})
            validation["checks"].append({"check": "Base paths validated", "passed": True})
            validation["checks"].append({"check": "Policies validated", "passed": True})
            
            if validation["warnings"]:
                validation["status"] = "warning"
            
            validations.append(validation)
        
        return validations
    
    async def validate_target_servers(self, edge_servers: List[Dict[str, Any]], 
                                       x_servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate target server migration"""
        validations = []
        
        edge_server_map = {s.get("name"): s for s in edge_servers}
        x_server_map = {s.get("name"): s for s in x_servers}
        
        for server_name in edge_server_map.keys():
            validation = {
                "resource_name": server_name,
                "status": "passed",
                "checks": [],
                "warnings": [],
                "errors": []
            }
            
            if server_name not in x_server_map:
                validation["status"] = "failed"
                validation["errors"].append(f"Target server '{server_name}' not found in Apigee X")
                validations.append(validation)
                continue
            
            edge_server = edge_server_map[server_name]
            x_server = x_server_map[server_name]
            
            # Validate host and port
            if edge_server.get("host") != x_server.get("host"):
                validation["errors"].append("Host mismatch")
                validation["status"] = "failed"
            
            if edge_server.get("port") != x_server.get("port"):
                validation["errors"].append("Port mismatch")
                validation["status"] = "failed"
            
            validation["checks"].append({"check": "Server exists", "passed": True})
            validation["checks"].append({"check": "Host matches", "passed": edge_server.get("host") == x_server.get("host")})
            validation["checks"].append({"check": "Port matches", "passed": edge_server.get("port") == x_server.get("port")})
            
            validations.append(validation)
        
        return validations
    
    async def validate_kvms(self, edge_kvms: List[Dict[str, Any]], 
                            x_kvms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate KVM migration"""
        validations = []
        
        edge_kvm_map = {k.get("name"): k for k in edge_kvms}
        x_kvm_map = {k.get("name"): k for k in x_kvms}
        
        for kvm_name in edge_kvm_map.keys():
            validation = {
                "resource_name": kvm_name,
                "status": "passed",
                "checks": [],
                "warnings": [],
                "errors": []
            }
            
            if kvm_name not in x_kvm_map:
                validation["status"] = "failed"
                validation["errors"].append(f"KVM '{kvm_name}' not found in Apigee X")
                validations.append(validation)
                continue
            
            edge_kvm = edge_kvm_map[kvm_name]
            x_kvm = x_kvm_map[kvm_name]
            
            # Validate entries
            edge_entries = edge_kvm.get("entries", {})
            x_entries = x_kvm.get("entries", {})
            
            if set(edge_entries.keys()) != set(x_entries.keys()):
                validation["warnings"].append("KVM entry keys differ")
                validation["status"] = "warning"
            
            validation["checks"].append({"check": "KVM exists", "passed": True})
            validation["checks"].append({"check": "Entry count matches", "passed": len(edge_entries) == len(x_entries)})
            
            validations.append(validation)
        
        return validations
    
    async def validate_api_products(self, edge_products: List[Dict[str, Any]], 
                                     x_products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate API product migration"""
        validations = []
        
        edge_product_map = {p.get("name"): p for p in edge_products}
        x_product_map = {p.get("name"): p for p in x_products}
        
        for product_name in edge_product_map.keys():
            validation = {
                "resource_name": product_name,
                "status": "passed",
                "checks": [{"check": "Product exists", "passed": product_name in x_product_map}],
                "warnings": [],
                "errors": []
            }
            
            if product_name not in x_product_map:
                validation["status"] = "failed"
                validation["errors"].append(f"API product '{product_name}' not found in Apigee X")
            
            validations.append(validation)
        
        return validations
    
    async def validate_developers(self, edge_devs: List[Dict[str, Any]], 
                                  x_devs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate developer migration"""
        validations = []
        
        edge_dev_map = {d.get("email"): d for d in edge_devs}
        x_dev_map = {d.get("email"): d for d in x_devs}
        
        for dev_email in edge_dev_map.keys():
            validation = {
                "resource_name": dev_email,
                "status": "passed",
                "checks": [{"check": "Developer exists", "passed": dev_email in x_dev_map}],
                "warnings": [],
                "errors": []
            }
            
            if dev_email not in x_dev_map:
                validation["status"] = "failed"
                validation["errors"].append(f"Developer '{dev_email}' not found in Apigee X")
            
            validations.append(validation)
        
        return validations
    
    def _count_total_checks(self, report: ValidationReport) -> int:
        """Count total validation checks"""
        total = 0
        for validations in [report.proxy_validations, report.target_server_validations, 
                           report.kvm_validations, report.api_product_validations, 
                           report.developer_validations]:
            for v in validations:
                total += len(v.get("checks", []))
        return total
    
    def _count_passed_checks(self, report: ValidationReport) -> int:
        """Count passed checks"""
        passed = 0
        for validations in [report.proxy_validations, report.target_server_validations, 
                           report.kvm_validations, report.api_product_validations, 
                           report.developer_validations]:
            for v in validations:
                passed += sum(1 for c in v.get("checks", []) if c.get("passed", False))
        return passed
    
    def _count_failed_checks(self, report: ValidationReport) -> int:
        """Count failed checks"""
        failed = 0
        for validations in [report.proxy_validations, report.target_server_validations, 
                           report.kvm_validations, report.api_product_validations, 
                           report.developer_validations]:
            for v in validations:
                if v.get("status") == "failed":
                    failed += 1
        return failed
    
    def _count_warning_checks(self, report: ValidationReport) -> int:
        """Count warnings"""
        warnings = 0
        for validations in [report.proxy_validations, report.target_server_validations, 
                           report.kvm_validations, report.api_product_validations, 
                           report.developer_validations]:
            for v in validations:
                warnings += len(v.get("warnings", []))
        return warnings
    
    def _generate_summary(self, report: ValidationReport) -> str:
        """Generate validation summary"""
        return f"Validation {report.status}: {report.passed_checks}/{report.total_checks} checks passed, "\
               f"{report.failed_checks} failed, {report.warning_checks} warnings"
