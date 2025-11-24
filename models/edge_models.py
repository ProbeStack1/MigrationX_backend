from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class ResourceType(str, Enum):
    PROXY = "proxy"
    SHARED_FLOW = "shared_flow"
    TARGET_SERVER = "target_server"
    KVM = "kvm"
    API_PRODUCT = "api_product"
    DEVELOPER = "developer"
    DEVELOPER_APP = "developer_app"
    ENVIRONMENT = "environment"
    ENV_GROUP = "env_group"
    COMPANY = "company"
    COMPANY_APP = "company_app"
    CUSTOM_REPORT = "custom_report"


class EdgeProxy(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    revision: str
    base_paths: List[str] = []
    policies: List[Dict[str, Any]] = []
    target_servers: List[str] = []
    resources: List[str] = []
    bundle_path: Optional[str] = None
    last_modified: Optional[datetime] = None


class EdgeSharedFlow(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    revision: str
    policies: List[Dict[str, Any]] = []
    bundle_path: Optional[str] = None


class EdgeTargetServer(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    host: str
    port: int
    is_enabled: bool = True
    ssl_info: Optional[Dict[str, Any]] = None
    environment: str


class EdgeKVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    encrypted: bool = False
    entries: Dict[str, str] = {}
    environment: Optional[str] = None
    scope: str = "environment"  # environment, organization, or api


class EdgeAPIProduct(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    display_name: str
    description: Optional[str] = None
    api_resources: List[str] = []
    proxies: List[str] = []
    environments: List[str] = []
    scopes: List[str] = []
    quota: Optional[str] = None
    quota_interval: Optional[str] = None
    quota_time_unit: Optional[str] = None
    attributes: List[Dict[str, str]] = []


class EdgeDeveloper(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    email: str
    first_name: str
    last_name: str
    user_name: str
    attributes: List[Dict[str, str]] = []
    apps: List[str] = []


class EdgeDeveloperApp(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    app_id: str
    developer_email: str
    api_products: List[str] = []
    credentials: List[Dict[str, Any]] = []
    callback_url: Optional[str] = None
    attributes: List[Dict[str, str]] = []
    status: str = "approved"


class EdgeEnvironment(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    description: Optional[str] = None
    properties: Dict[str, str] = {}


class EdgeCompany(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    display_name: str
    status: str
    attributes: List[Dict[str, str]] = []
    apps: List[str] = []


class EdgeOrgConfig(BaseModel):
    name: str
    base_url: str
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    environments: List[str] = []
