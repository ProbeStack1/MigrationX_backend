"""Assessment engine to analyze migration readiness of Edge resources"""
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class MigrationAssessment:
    """Assess migration readiness of Apigee Edge resources"""
    
    # Policies that are not supported in Apigee X
    UNSUPPORTED_POLICIES = {
        "SOAPMessageValidation": "Not supported in Apigee X",
        "XMLToJSON": "Deprecated - use other methods",
        "JSONToXML": "Deprecated - use other methods",
        "StatisticsCollector": "Use Analytics API instead",
        "AccessEntity": "Limited support in X",
    }
    
    # Policies that need transformation
    TRANSFORMATION_NEEDED = {
        "JavaCallout": "Requires conversion to Extension Callout",
        "Python": "Requires conversion to Extension Callout",
        "Javascript": "Review for compatibility",
    }
    
    # Policies with potential issues
    WARNING_POLICIES = {
        "ServiceCallout": "Check target server compatibility",
        "MessageLogging": "Verify logging configuration",
        "Script": "Review and test thoroughly",
    }
    
    def __init__(self):
        self.assessment_results = {
            "summary": {},
            "proxy_assessments": [],
            "shared_flow_assessments": [],
            "target_server_assessments": [],
            "kvm_assessments": [],
            "api_product_assessments": [],
            "app_assessments": [],
            "developer_assessments": [],
            "overall_status": "ready",  # ready, needs_attention, blocked
            "total_issues": 0,
            "total_warnings": 0
        }
    
    def assess_all_resources(self, edge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform complete assessment of all resources"""
        
        # Assess proxies
        if edge_data.get("proxies"):
            for proxy in edge_data["proxies"]:
                assessment = self._assess_proxy(proxy)
                self.assessment_results["proxy_assessments"].append(assessment)
        
        # Assess shared flows
        if edge_data.get("shared_flows"):
            for shared_flow in edge_data["shared_flows"]:
                assessment = self._assess_shared_flow(shared_flow)
                self.assessment_results["shared_flow_assessments"].append(assessment)
        
        # Assess target servers
        if edge_data.get("target_servers"):
            for ts in edge_data["target_servers"]:
                assessment = self._assess_target_server(ts)
                self.assessment_results["target_server_assessments"].append(assessment)
        
        # Assess KVMs
        if edge_data.get("kvms"):
            for kvm in edge_data["kvms"]:
                assessment = self._assess_kvm(kvm)
                self.assessment_results["kvm_assessments"].append(assessment)
        
        # Assess API Products
        if edge_data.get("api_products"):
            for product in edge_data["api_products"]:
                assessment = self._assess_api_product(product)
                self.assessment_results["api_product_assessments"].append(assessment)
        
        # Assess Apps
        if edge_data.get("apps"):
            for app in edge_data["apps"]:
                assessment = self._assess_app(app)
                self.assessment_results["app_assessments"].append(assessment)

        # Assess Developers
        if edge_data.get("developers"):
            for dev in edge_data["developers"]:
                assessment = self._assess_developer(dev)
                self.assessment_results["developer_assessments"].append(assessment)
        
        # Calculate summary
        self._calculate_summary(edge_data)
        
        # Determine overall status
        self._determine_overall_status()
        
        return self.assessment_results
    
    def _assess_proxy(self, proxy: Dict[str, Any]) -> Dict[str, Any]:
        """Assess a single API proxy"""
        assessment = {
            "name": proxy.get("name"),
            "type": "API Proxy",
            "status": "ready",  # ready, warning, blocked
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "policy_analysis": {
                "total": len(proxy.get("policies", [])),
                "unsupported": 0,
                "needs_transformation": 0,
                "warnings": 0
            }
        }
        
        policies = proxy.get("policies", [])
        
        # Analyze each policy
        for policy in policies:
            policy_type = policy.get("type")
            policy_name = policy.get("name")
            
            # Check for unsupported policies
            if policy_type in self.UNSUPPORTED_POLICIES:
                assessment["issues"].append({
                    "policy": policy_name,
                    "type": policy_type,
                    "severity": "high",
                    "message": self.UNSUPPORTED_POLICIES[policy_type]
                })
                assessment["policy_analysis"]["unsupported"] += 1
                assessment["status"] = "blocked"
            
            # Check for policies needing transformation
            elif policy_type in self.TRANSFORMATION_NEEDED:
                assessment["warnings"].append({
                    "policy": policy_name,
                    "type": policy_type,
                    "severity": "medium",
                    "message": self.TRANSFORMATION_NEEDED[policy_type]
                })
                assessment["policy_analysis"]["needs_transformation"] += 1
                if assessment["status"] == "ready":
                    assessment["status"] = "warning"
            
            # Check for warning policies
            elif policy_type in self.WARNING_POLICIES:
                assessment["warnings"].append({
                    "policy": policy_name,
                    "type": policy_type,
                    "severity": "low",
                    "message": self.WARNING_POLICIES[policy_type]
                })
                assessment["policy_analysis"]["warnings"] += 1
        
        # Generate recommendations
        if assessment["policy_analysis"]["unsupported"] > 0:
            assessment["recommendations"].append(
                f"Remove or replace {assessment['policy_analysis']['unsupported']} unsupported policy(ies)"
            )
        
        if assessment["policy_analysis"]["needs_transformation"] > 0:
            assessment["recommendations"].append(
                f"Transform {assessment['policy_analysis']['needs_transformation']} policy(ies) to Extension Callouts"
            )
        
        if len(policies) == 0:
            assessment["warnings"].append({
                "policy": "N/A",
                "type": "Configuration",
                "severity": "low",
                "message": "Proxy has no policies - verify this is intentional"
            })
        
        return assessment
    
    def _assess_shared_flow(self, shared_flow: Dict[str, Any]) -> Dict[str, Any]:
        """Assess a shared flow"""
        assessment = {
            "name": shared_flow.get("name"),
            "type": "Shared Flow",
            "status": "ready",
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "policy_analysis": {
                "total": len(shared_flow.get("policies", [])),
                "unsupported": 0,
                "needs_transformation": 0,
                "warnings": 0
            }
        }
        
        policies = shared_flow.get("policies", [])
        
        # Analyze each policy (same logic as proxy)
        for policy in policies:
            policy_type = policy.get("type")
            policy_name = policy.get("name")
            
            if policy_type in self.UNSUPPORTED_POLICIES:
                assessment["issues"].append({
                    "policy": policy_name,
                    "type": policy_type,
                    "severity": "high",
                    "message": self.UNSUPPORTED_POLICIES[policy_type]
                })
                assessment["policy_analysis"]["unsupported"] += 1
                assessment["status"] = "blocked"
            
            elif policy_type in self.TRANSFORMATION_NEEDED:
                assessment["warnings"].append({
                    "policy": policy_name,
                    "type": policy_type,
                    "severity": "medium",
                    "message": self.TRANSFORMATION_NEEDED[policy_type]
                })
                assessment["policy_analysis"]["needs_transformation"] += 1
                if assessment["status"] == "ready":
                    assessment["status"] = "warning"
            
            elif policy_type in self.WARNING_POLICIES:
                assessment["warnings"].append({
                    "policy": policy_name,
                    "type": policy_type,
                    "severity": "low",
                    "message": self.WARNING_POLICIES[policy_type]
                })
                assessment["policy_analysis"]["warnings"] += 1
        
        if len(policies) == 0:
            assessment["warnings"].append({
                "policy": "N/A",
                "type": "Configuration",
                "severity": "low",
                "message": "Shared flow has no policies - verify this is intentional"
            })
        
        return assessment
    
    def _assess_target_server(self, target_server: Dict[str, Any]) -> Dict[str, Any]:
        """Assess a target server"""
        assessment = {
            "name": target_server.get("name"),
            "type": "Target Server",
            "status": "ready",
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Check SSL configuration
        if not target_server.get("sslEnabled"):
            assessment["warnings"].append({
                "field": "SSL",
                "severity": "medium",
                "message": "SSL not enabled - consider enabling for security"
            })
            assessment["status"] = "warning"
        
        # Check if using internal IP
        host = target_server.get("host", "")
        if host.startswith("10.") or host.startswith("192.168.") or host.startswith("172."):
            assessment["warnings"].append({
                "field": "Host",
                "severity": "high",
                "message": "Using private IP - ensure network connectivity in Apigee X"
            })
            assessment["recommendations"].append(
                "Verify network connectivity or use Cloud Load Balancer"
            )
        
        # Check port
        port = target_server.get("port")
        if port and port not in [80, 443, 8080, 8443]:
            assessment["warnings"].append({
                "field": "Port",
                "severity": "low",
                "message": f"Non-standard port {port} - verify firewall rules"
            })
        
        return assessment
    
    def _assess_kvm(self, kvm: Dict[str, Any]) -> Dict[str, Any]:
        """Assess a KVM"""
        assessment = {
            "name": kvm.get("name"),
            "type": "KVM",
            "status": "ready",
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Check if encrypted
        if not kvm.get("encrypted"):
            assessment["warnings"].append({
                "field": "Encryption",
                "severity": "medium",
                "message": "KVM is not encrypted - consider encryption for sensitive data"
            })
        
        # Check entry count
        entries = kvm.get("entries", 0)
        if entries == 0:
            assessment["warnings"].append({
                "field": "Entries",
                "severity": "low",
                "message": "KVM has no entries"
            })
        
        return assessment
    
    def _assess_api_product(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """Assess an API product"""
        assessment = {
            "name": product.get("name"),
            "type": "API Product",
            "status": "ready",
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Check if product has proxies
        proxies = product.get("proxies", [])
        if len(proxies) == 0:
            assessment["warnings"].append({
                "field": "Proxies",
                "severity": "medium",
                "message": "API Product has no proxies associated"
            })
            assessment["status"] = "warning"
        
        return assessment
    
    def _assess_developer(self, developer: Dict[str, Any]) -> Dict[str, Any]:
        """Assess a single developer for migration"""
        issues = []
        warnings = []
        status = "ready"
        
        # Check required fields
        if not developer.get("email"):
            issues.append("Missing required field: email")
            status = "blocked"
        
        if not developer.get("firstName") or not developer.get("lastName"):
            warnings.append("Missing name fields - may need manual review")
            if status == "ready":
                status = "warning"
        
        # Check for special characters in email
        email = developer.get("email", "")
        if email and not email.strip():
            issues.append("Email field is empty or contains only whitespace")
            status = "blocked"
        
        return {
            "name": email or "Unknown Developer",
            "type": "developer",
            "status": status,
            "issues": issues,
            "warnings": warnings,
            "recommendations": []
        }

    def _assess_app(self, app: Dict[str, Any]) -> Dict[str, Any]:
        """Assess a single developer app for migration"""
        issues = []
        warnings = []
        status = "ready"
        
        # Check required fields
        if not app.get("name"):
            issues.append("Missing required field: name")
            status = "blocked"
        
        if not app.get("developerId"):
            warnings.append("Missing developerId - app may need to be reassigned")
            if status == "ready":
                status = "warning"
        
        # Check API products
        api_products = app.get("apiProducts", [])
        if not api_products:
            warnings.append("No API products associated - app may be inactive")
            if status == "ready":
                status = "warning"
        
        # Check credentials
        credentials = app.get("credentials", 0)
        if credentials == 0:
            warnings.append("No credentials found - new credentials will be generated")
            if status == "ready":
                status = "warning"
        
        return {
            "name": app.get("name", "Unknown App"),
            "type": "app",
            "status": status,
            "issues": issues,
            "warnings": warnings,
            "recommendations": [],
            "api_products": api_products,
            "credentials_count": credentials
        }


    def _calculate_summary(self, edge_data: Dict[str, Any]):
        """Calculate assessment summary"""
        total_issues = 0
        total_warnings = 0
        
        for assessment in self.assessment_results["proxy_assessments"]:
            total_issues += len(assessment.get("issues", []))
            total_warnings += len(assessment.get("warnings", []))
        
        for assessment in self.assessment_results["shared_flow_assessments"]:
            total_issues += len(assessment.get("issues", []))
            total_warnings += len(assessment.get("warnings", []))
        
        for assessment in self.assessment_results["target_server_assessments"]:
            total_issues += len(assessment.get("issues", []))
            total_warnings += len(assessment.get("warnings", []))
        
        for assessment in self.assessment_results["kvm_assessments"]:
            total_issues += len(assessment.get("issues", []))
            total_warnings += len(assessment.get("warnings", []))
        
        self.assessment_results["total_issues"] = total_issues
        self.assessment_results["total_warnings"] = total_warnings
        
        # Count by status (include both proxies and shared flows)
        ready_count = sum(1 for a in self.assessment_results["proxy_assessments"] if a["status"] == "ready")
        ready_count += sum(1 for a in self.assessment_results["shared_flow_assessments"] if a["status"] == "ready")
        
        warning_count = sum(1 for a in self.assessment_results["proxy_assessments"] if a["status"] == "warning")
        warning_count += sum(1 for a in self.assessment_results["shared_flow_assessments"] if a["status"] == "warning")
        
        blocked_count = sum(1 for a in self.assessment_results["proxy_assessments"] if a["status"] == "blocked")
        blocked_count += sum(1 for a in self.assessment_results["shared_flow_assessments"] if a["status"] == "blocked")
        
        self.assessment_results["summary"] = {
            "total_proxies": len(edge_data.get("proxies", [])),
            "total_shared_flows": len(edge_data.get("shared_flows", [])),
            "total_target_servers": len(edge_data.get("target_servers", [])),
            "total_kvms": len(edge_data.get("kvms", [])),
            "total_api_products": len(edge_data.get("api_products", [])),
            "total_apps": len(edge_data.get("apps", [])),
            "total_developers": len(edge_data.get("developers", [])),
            "ready_to_migrate": ready_count,
            "needs_attention": warning_count,
            "blocked": blocked_count,
            "total_issues": total_issues,
            "total_warnings": total_warnings
        }
    
    def _determine_overall_status(self):
        """Determine overall migration status"""
        if self.assessment_results["total_issues"] > 0:
            self.assessment_results["overall_status"] = "blocked"
        elif self.assessment_results["total_warnings"] > 0:
            self.assessment_results["overall_status"] = "needs_attention"
        else:
            self.assessment_results["overall_status"] = "ready"
