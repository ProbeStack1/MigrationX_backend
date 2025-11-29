"""Pydantic models for Apigee configuration requests and responses"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Literal, Dict, Any
from datetime import datetime


class ApigeeEdgeConfigRequest(BaseModel):
    """Request model for Apigee Edge configuration"""
    model_config = ConfigDict(extra="forbid")
    
    apigee_type: Literal["Edge"] = "Edge"
    org_id: str = Field(..., description="Apigee Edge organization ID", min_length=1)
    base_url: str = Field(
        default="https://api.enterprise.apigee.com",
        description="Management API base URL"
    )
    username: str = Field(..., description="Username for basic authentication", min_length=1)
    password: str = Field(..., description="Password for basic authentication", min_length=1)
    environment: Optional[str] = Field(None, description="Environment name (e.g., prod, test)")
    
    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


class ApigeeXConfigRequest(BaseModel):
    """Request model for Apigee X configuration"""
    model_config = ConfigDict(extra="forbid")
    
    apigee_type: Literal["X"] = "X"
    project_id: str = Field(..., description="GCP Project ID", min_length=1)
    base_url: str = Field(
        default="https://apigee.googleapis.com",
        description="Management API base URL"
    )
    organization: str = Field(..., description="Apigee X organization name", min_length=1)
    environment: Optional[str] = Field(None, description="Environment name (e.g., prod, eval)")
    
    # Authentication options - either service_account_json or oauth_token
    service_account_json: Optional[str] = Field(
        None,
        description="Service account JSON key as string (for service account auth)"
    )
    oauth_token: Optional[str] = Field(
        None,
        description="OAuth2 access token (for OAuth authentication)"
    )
    
    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v
    
    @field_validator("service_account_json", "oauth_token")
    @classmethod
    def validate_auth(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure at least one auth method is provided"""
        # This will be validated at the request level
        return v


class ApigeeConfigRequest(BaseModel):
    """Unified request model for both Edge and X configurations"""
    model_config = ConfigDict(extra="allow")
    
    # Unified fields (primary) - all optional to allow mapping from legacy fields
    gateway_type: Optional[Literal["Edge", "X"]] = Field(None, description="Type of Apigee gateway (Edge or X)")
    organization: Optional[str] = Field(None, description="Organization name")
    login_url: Optional[str] = Field(None, description="Management API base URL (login URL)")
    username: Optional[str] = Field(None, description="Username for authentication")
    password: Optional[str] = Field(None, description="Password for authentication (for Edge or X with basic auth)")
    accessToken: Optional[str] = Field(None, description="Access token for authentication (alternative to password for X)")
    environment: Optional[str] = Field(None, description="Environment name (e.g., prod, eval, sandbox)")
    
    # Legacy fields for backward compatibility (will be mapped to unified fields)
    apigee_type: Optional[Literal["Edge", "X"]] = None
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    base_url: Optional[str] = None
    oauth_token: Optional[str] = None
    service_account_json: Optional[str] = None
    
    @field_validator("login_url", "base_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format"""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v
    
    @field_validator("gateway_type", "apigee_type")
    @classmethod
    def validate_gateway_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate gateway_type"""
        if v and v not in ["Edge", "X"]:
            raise ValueError("gateway_type/apigee_type must be either 'Edge' or 'X'")
        return v


class ApigeeConfigResponse(BaseModel):
    """Response model for successful configuration"""
    model_config = ConfigDict(extra="forbid")
    
    success: bool = True
    message: str
    apigee_type: Literal["Edge", "X"]
    org_id: Optional[str] = None
    organization: Optional[str] = None
    project_id: Optional[str] = None
    environment: Optional[str] = None
    base_url: str
    verified_at: datetime
    stored: bool = True


class ApigeeConfigErrorResponse(BaseModel):
    """Error response model"""
    model_config = ConfigDict(extra="forbid")
    
    success: bool = False
    error: str
    error_code: str
    details: Optional[Dict[str, Any]] = None

