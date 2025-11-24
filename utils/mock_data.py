"""Mock data generator for demo mode"""
import json
import random
from typing import List, Dict, Any
from models.edge_models import (
    EdgeProxy, EdgeSharedFlow, EdgeTargetServer, EdgeKVM,
    EdgeAPIProduct, EdgeDeveloper, EdgeDeveloperApp, EdgeEnvironment
)


class MockDataGenerator:
    """Generate realistic mock data for Apigee Edge resources"""
    
    SAMPLE_POLICIES = [
        {"name": "AssignMessage-SetHeaders", "type": "AssignMessage"},
        {"name": "VerifyAPIKey", "type": "VerifyAPIKey"},
        {"name": "Quota-1", "type": "Quota"},
        {"name": "SpikeArrest-1", "type": "SpikeArrest"},
        {"name": "JSONThreatProtection", "type": "JSONThreatProtection"},
        {"name": "XMLToJSON-1", "type": "XMLToJSON"},
        {"name": "ServiceCallout-Backend", "type": "ServiceCallout"},
        {"name": "ExtractVariables-1", "type": "ExtractVariables"},
        {"name": "RaiseFault-InvalidRequest", "type": "RaiseFault"},
        {"name": "JavaCallout-Transform", "type": "JavaCallout"},  # Needs transformation
        {"name": "MessageLogging-1", "type": "MessageLogging"},
    ]
    
    SAMPLE_PROXY_NAMES = [
        "customer-api-v1",
        "order-management-api",
        "payment-gateway-proxy",
        "product-catalog-api",
        "auth-service-proxy",
        "notification-api-v2",
        "analytics-data-api",
        "inventory-service",
    ]
    
    def generate_proxies(self, count: int = 5) -> List[EdgeProxy]:
        """Generate mock API proxies"""
        proxies = []
        for i in range(count):
            name = self.SAMPLE_PROXY_NAMES[i % len(self.SAMPLE_PROXY_NAMES)]
            proxy = EdgeProxy(
                name=name,
                revision=str(random.randint(1, 10)),
                base_paths=[f"/v1/{name.split('-')[0]}", f"/{name}"],
                policies=random.sample(self.SAMPLE_POLICIES, random.randint(3, 7)),
                target_servers=[f"backend-{random.randint(1, 3)}"],
                resources=["jsc://transform.js", "py://validator.py"],
                bundle_path=f"/mock/bundles/{name}.zip"
            )
            proxies.append(proxy)
        return proxies
    
    def generate_shared_flows(self, count: int = 3) -> List[EdgeSharedFlow]:
        """Generate mock shared flows"""
        flow_names = ["security-common", "logging-common", "cors-handler"]
        flows = []
        for i in range(count):
            flow = EdgeSharedFlow(
                name=flow_names[i % len(flow_names)],
                revision=str(random.randint(1, 5)),
                policies=random.sample(self.SAMPLE_POLICIES, random.randint(2, 5)),
                bundle_path=f"/mock/bundles/{flow_names[i % len(flow_names)]}.zip"
            )
            flows.append(flow)
        return flows
    
    def generate_target_servers(self, count: int = 3) -> List[EdgeTargetServer]:
        """Generate mock target servers"""
        servers = []
        for i in range(1, count + 1):
            server = EdgeTargetServer(
                name=f"backend-{i}",
                host=f"backend{i}.example.com",
                port=443 if i % 2 == 0 else 8080,
                is_enabled=True,
                ssl_info={"enabled": i % 2 == 0, "protocols": ["TLSv1.2", "TLSv1.3"]} if i % 2 == 0 else None,
                environment="prod"
            )
            servers.append(server)
        return servers
    
    def generate_kvms(self, count: int = 4) -> List[EdgeKVM]:
        """Generate mock KVMs"""
        kvm_configs = [
            {"name": "api-config", "encrypted": False, "entries": {"timeout": "30000", "retries": "3", "base_url": "https://api.example.com"}},
            {"name": "service-credentials", "encrypted": True, "entries": {"api_key": "encrypted_key_value", "client_secret": "encrypted_secret"}},
            {"name": "feature-flags", "encrypted": False, "entries": {"enable_cache": "true", "enable_logging": "true", "rate_limit": "1000"}},
            {"name": "backend-endpoints", "encrypted": False, "entries": {"primary": "https://primary.api.com", "secondary": "https://secondary.api.com"}},
        ]
        kvms = []
        for i in range(min(count, len(kvm_configs))):
            config = kvm_configs[i]
            kvm = EdgeKVM(
                name=config["name"],
                encrypted=config["encrypted"],
                entries=config["entries"],
                environment="prod",
                scope="environment"
            )
            kvms.append(kvm)
        return kvms
    
    def generate_api_products(self, count: int = 3) -> List[EdgeAPIProduct]:
        """Generate mock API products"""
        product_configs = [
            {
                "name": "premium-api-product",
                "display_name": "Premium API Product",
                "description": "Premium tier with unlimited access",
                "proxies": ["customer-api-v1", "order-management-api"],
                "quota": "10000",
                "quota_interval": "1",
                "quota_time_unit": "hour"
            },
            {
                "name": "basic-api-product",
                "display_name": "Basic API Product",
                "description": "Basic tier with rate limiting",
                "proxies": ["customer-api-v1"],
                "quota": "1000",
                "quota_interval": "1",
                "quota_time_unit": "hour"
            },
            {
                "name": "internal-api-product",
                "display_name": "Internal API Product",
                "description": "For internal services only",
                "proxies": ["analytics-data-api", "inventory-service"],
                "quota": None,
                "quota_interval": None,
                "quota_time_unit": None
            },
        ]
        
        products = []
        for i in range(min(count, len(product_configs))):
            config = product_configs[i]
            product = EdgeAPIProduct(
                name=config["name"],
                display_name=config["display_name"],
                description=config["description"],
                api_resources=["/", "/**"],
                proxies=config["proxies"],
                environments=["prod", "test"],
                scopes=["read", "write"] if i == 0 else ["read"],
                quota=config["quota"],
                quota_interval=config["quota_interval"],
                quota_time_unit=config["quota_time_unit"],
                attributes=[{"name": "access", "value": "public"}]
            )
            products.append(product)
        return products
    
    def generate_developers(self, count: int = 3) -> List[EdgeDeveloper]:
        """Generate mock developers"""
        developer_data = [
            {"email": "john.doe@example.com", "first_name": "John", "last_name": "Doe", "user_name": "jdoe"},
            {"email": "jane.smith@example.com", "first_name": "Jane", "last_name": "Smith", "user_name": "jsmith"},
            {"email": "bob.wilson@example.com", "first_name": "Bob", "last_name": "Wilson", "user_name": "bwilson"},
        ]
        
        developers = []
        for i in range(min(count, len(developer_data))):
            data = developer_data[i]
            developer = EdgeDeveloper(
                email=data["email"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                user_name=data["user_name"],
                attributes=[{"name": "company", "value": "Example Corp"}],
                apps=[f"{data['user_name']}-app-1", f"{data['user_name']}-app-2"]
            )
            developers.append(developer)
        return developers
    
    def generate_developer_apps(self, count: int = 5) -> List[EdgeDeveloperApp]:
        """Generate mock developer apps"""
        apps = []
        developers = ["john.doe@example.com", "jane.smith@example.com", "bob.wilson@example.com"]
        
        for i in range(count):
            app = EdgeDeveloperApp(
                name=f"app-{i+1}",
                app_id=f"app-id-{random.randint(10000, 99999)}",
                developer_email=developers[i % len(developers)],
                api_products=["premium-api-product" if i % 2 == 0 else "basic-api-product"],
                credentials=[
                    {
                        "consumerKey": f"key-{random.randint(100000, 999999)}",
                        "consumerSecret": f"secret-{random.randint(100000, 999999)}",
                        "status": "approved"
                    }
                ],
                callback_url=f"https://app{i+1}.example.com/callback",
                status="approved"
            )
            apps.append(app)
        return apps
    
    def generate_environments(self) -> List[EdgeEnvironment]:
        """Generate mock environments"""
        envs = [
            EdgeEnvironment(
                name="prod",
                description="Production environment",
                properties={"cache_enabled": "true", "log_level": "info"}
            ),
            EdgeEnvironment(
                name="test",
                description="Test environment",
                properties={"cache_enabled": "false", "log_level": "debug"}
            ),
        ]
        return envs
    
    def generate_complete_export(self) -> Dict[str, Any]:
        """Generate a complete mock export with all resource types"""
        return {
            "proxies": [p.model_dump() for p in self.generate_proxies(5)],
            "shared_flows": [sf.model_dump() for sf in self.generate_shared_flows(3)],
            "target_servers": [ts.model_dump() for ts in self.generate_target_servers(3)],
            "kvms": [kvm.model_dump() for kvm in self.generate_kvms(4)],
            "api_products": [ap.model_dump() for ap in self.generate_api_products(3)],
            "developers": [d.model_dump() for d in self.generate_developers(3)],
            "developer_apps": [da.model_dump() for da in self.generate_developer_apps(5)],
            "environments": [e.model_dump() for e in self.generate_environments()],
        }
