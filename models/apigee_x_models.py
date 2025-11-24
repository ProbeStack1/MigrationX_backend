from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Any
from datetime import datetime


class ApigeeXProxy(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    revision: str
    base_paths: List[str] = []
    policies: List[Dict[str, Any]] = []
    target_endpoints: List[Dict[str, Any]] = []
    proxy_endpoints: List[Dict[str, Any]] = []
    bundle_path: Optional[str] = None
    deployed: bool = False
    deployed_revision: Optional[str] = None


class ApigeeXSharedFlow(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    revision: str
    policies: List[Dict[str, Any]] = []
    bundle_path: Optional[str] = None


class ApigeeXTargetServer(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    host: str
    port: int
    protocol: str = "HTTP"
    is_enabled: bool = True
    ssl_info: Optional[Dict[str, Any]] = None


class ApigeeXKVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    name: str
    encrypted: bool = False
    entries: Dict[str, str] = {}


class ApigeeXAPIProduct(BaseModel):
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


class ApigeeXConfig(BaseModel):
    project_id: str
    organization: str
    location: str = "us-central1"
    service_account_key_path: Optional[str] = None
    environments: List[str] = []
