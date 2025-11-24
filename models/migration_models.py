from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from enum import Enum
import uuid


class MigrationStatus(str, Enum):
    PENDING = "pending"
    EXPORTING = "exporting"
    TRANSFORMING = "transforming"
    IMPORTING = "importing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class ResourceStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


class MigrationResource(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    resource_type: str
    resource_name: str
    status: ResourceStatus = ResourceStatus.PENDING
    edge_data: Optional[Dict[str, Any]] = None
    x_data: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    warnings: List[str] = []
    transformation_notes: List[str] = []


class MigrationJob(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    status: MigrationStatus = MigrationStatus.PENDING
    edge_org: str
    edge_env: str
    apigee_x_org: str
    apigee_x_env: str
    dry_run: bool = False
    
    resources: List[MigrationResource] = []
    
    # Progress tracking
    total_resources: int = 0
    completed_resources: int = 0
    failed_resources: int = 0
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Logs
    logs: List[str] = []
    errors: List[str] = []
    warnings: List[str] = []


class MigrationJobCreate(BaseModel):
    name: str
    edge_org: str
    edge_env: str
    apigee_x_org: str
    apigee_x_env: str
    dry_run: bool = False
    resource_types: List[str] = []  # Filter specific resource types


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    migration_job_id: str
    status: str = "passed"  # passed, failed, warnings
    
    proxy_validations: List[Dict[str, Any]] = []
    kvm_validations: List[Dict[str, Any]] = []
    target_server_validations: List[Dict[str, Any]] = []
    api_product_validations: List[Dict[str, Any]] = []
    developer_validations: List[Dict[str, Any]] = []
    
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str = ""


class DiffResult(BaseModel):
    resource_type: str
    resource_name: str
    differences: List[Dict[str, Any]] = []
    status: str = "identical"  # identical, modified, added, removed
