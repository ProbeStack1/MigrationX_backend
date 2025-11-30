from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone
import asyncio
from fastapi import HTTPException, BackgroundTasks
from datetime import datetime, timezone
import asyncio
import uvicorn
# In-memory storage when MongoDB is not available
_in_memory_config = None
# Import migration models and engine
from models.migration_models import MigrationJob, MigrationJobCreate, ValidationReport, DiffResult
from models.apigee_config_models import (
    ApigeeConfigRequest, ApigeeConfigResponse, ApigeeConfigErrorResponse,
    ApigeeEdgeConfigRequest, ApigeeXConfigRequest
)
from migration.migration_engine import MigrationEngine
from migration.assessment_engine import MigrationAssessment
from migration.apigee_x_migrator import ApigeeXMigrator
from migration.apigee_edge_client import ApigeeEdgeClient
from migration.apigee_x_client import ApigeeXClient
from utils.diff_calculator import DiffCalculator
from utils.mock_data import MockDataGenerator
from utils.credential_encryption import encrypt_credential, mask_credential
import json

# Firestore import (only for /api/config/apigee endpoint)
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    firestore = None


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configuration flags
# Set ENABLE_APIGEE_VERIFICATION=true to enable real Apigee connection verification
# When false, configuration is stored without actual API verification (for development/testing)
ENABLE_APIGEE_VERIFICATION = os.environ.get("ENABLE_APIGEE_VERIFICATION", "false").strip().lower() in ["true", "1", "yes"]

# MongoDB connection (optional)
mongo_url = os.environ.get("MONGO_URL", "").strip().lower()

# Check if MongoDB is disabled
if mongo_url in ["none", "no", "false", "0", ""]:
    print("⚠ MongoDB disabled – running in NO-DATABASE mode")
    client = None
    db = None

else:
    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
        db = client[os.environ.get('DB_NAME', 'apigee_migration')]
        client.server_info()  # Test the connection
        print("✓ MongoDB connected")
    except Exception as e:
        print(f"⚠ MongoDB not available: {e}")
        print("⚠ Running in no-database mode (configuration will not persist)")
        client = None
        db = None

# Firestore connection (ONLY for /api/config/apigee endpoint)
# This is separate from MongoDB to avoid impacting other endpoints
firestore_db = None
if FIRESTORE_AVAILABLE:
    firestore_credentials_path = os.environ.get("FIRESTORE_CREDENTIALS", str(ROOT_DIR / "credentials" / "firestore-credentials.json"))
    firestore_project_id = os.environ.get("FIRESTORE_PROJECT_ID", None)
    
    try:
        if os.path.exists(firestore_credentials_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = firestore_credentials_path
            if firestore_project_id:
                firestore_db = firestore.Client(project=firestore_project_id)
            else:
                firestore_db = firestore.Client()
            print("✓ Firestore connected (for /api/config/apigee endpoint)")
        else:
            print(f"⚠ Firestore credentials not found at {firestore_credentials_path}")
            print("⚠ /api/config/apigee will use in-memory storage")
            firestore_db = None
    except Exception as e:
        print(f"⚠ Firestore not available: {e}")
        print("⚠ /api/config/apigee will use in-memory storage")
        firestore_db = None
else:
    print("⚠ google-cloud-firestore not installed - /api/config/apigee will use in-memory storage")

# Create the main app without a prefix
app = FastAPI(
    title="Apigee Edge to X Migration API",
    description="""
    API for migrating resources from Apigee Edge to Apigee X.
    
    ## Configuration
    
    This API supports configuration for both Apigee Edge and Apigee X platforms.
    Use the `/api/config/apigee` endpoint to configure and verify connections.
    
    ## Authentication
    
    - **Apigee Edge**: Uses Basic Authentication (username/password)
    - **Apigee X**: Uses OAuth2 or Service Account authentication
    """,
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Configuration",
            "description": "Apigee configuration and connection management"
        },
        {
            "name": "Migration",
            "description": "Migration job management and execution"
        },
        {
            "name": "Discovery",
            "description": "Resource discovery and assessment"
        }
    ]
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# In-memory storage for active migration jobs (in production, use DB)
active_jobs: Dict[str, MigrationEngine] = {}


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

migration_jobs_memory = []
# === Health Check Routes ===
@api_router.get("/")
async def root():
    return {
        "message": "Apigee Edge to X Migration API",
        "version": "1.0.0",
        "status": "running"
    }

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# === Migration Job Routes ===

@api_router.post("/migrations", response_model=MigrationJob)
async def create_migration_job(job_create: MigrationJobCreate):
    job = MigrationJob(
        name=job_create.name,
        edge_org=job_create.edge_org,
        edge_env=job_create.edge_env,
        apigee_x_org=job_create.apigee_x_org,
        apigee_x_env=job_create.apigee_x_env,
        dry_run=job_create.dry_run
    )

    # Run assessment immediately
    from utils.edge_data_parser import EdgeDataParser
    from migration.dependency_analyzer import DependencyAnalyzer
    parser = EdgeDataParser()
    edge_data = parser.parse_all()
    
    assessor = MigrationAssessment()
    assessment = assessor.assess_all_resources(edge_data)
    
    # Combine all resource assessments into one list for the job
    job.resources = (
        assessment.get("proxy_assessments", []) +
        assessment.get("shared_flow_assessments", []) +
        assessment.get("target_server_assessments", []) +
        assessment.get("kvm_assessments", []) +
        assessment.get("api_product_assessments", []) +
        assessment.get("developer_assessments", [])  # if exists
    )
    
    migration_jobs_memory.append(job.model_dump(exclude_unset=False))
    return job

@api_router.get("/migrations", response_model=List[MigrationJob])
async def list_migration_jobs():
    # Convert timestamps from strings → datetime
    jobs = []
    for job in migration_jobs_memory:
        j = job.copy()
        
        for key in ["created_at", "started_at", "completed_at"]:
            if isinstance(j.get(key), str):
                j[key] = datetime.fromisoformat(j[key])
        
        jobs.append(j)

    return jobs


@api_router.get("/migrations/{job_id}", response_model=MigrationJob)
async def get_migration_job(job_id: str):
    # Look up in memory
    job_dict = next((j for j in migration_jobs_memory if j["id"] == job_id), None)

    if not job_dict:
        raise HTTPException(status_code=404, detail="Migration job not found")

    # Convert timestamps safely
    j = job_dict.copy()
    for key in ["created_at", "started_at", "completed_at"]:
        if j.get(key) and isinstance(j[key], str):
            j[key] = datetime.fromisoformat(j[key])

    return MigrationJob(**j)

@api_router.post("/migrations/{job_id}/start")
async def start_migration(job_id: str, background_tasks: BackgroundTasks):
    """Start a migration job safely in NO-DATABASE mode"""

    # 1️⃣ Find job in memory
    job_dict = next((j for j in migration_jobs_memory if j["id"] == job_id), None)
    if not job_dict:
        raise HTTPException(status_code=404, detail="Migration job not found")

    # 2️⃣ Ensure list fields exist
    job_dict.setdefault("resources", [])
    job_dict.setdefault("logs", [])
    job_dict.setdefault("errors", [])
    job_dict.setdefault("warnings", [])

    # 3️⃣ Filter only known fields for MigrationJob
    allowed_fields = set(MigrationJob.model_fields.keys())
    safe_dict = {k: v for k, v in job_dict.items() if k in allowed_fields}

    # 4️⃣ Define SafeMigrationJob ignoring extra fields inside nested dicts
    class SafeMigrationJob(MigrationJob):
        model_config = {"extra": "ignore"}

    try:
        job = SafeMigrationJob(**safe_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse job: {e}")

    # 5️⃣ Set running state
    job.started_at = datetime.now(timezone.utc)
    job.status = "running"

    # 6️⃣ Update in-memory job
    for i, j in enumerate(migration_jobs_memory):
        if j["id"] == job_id:
            migration_jobs_memory[i] = job.model_dump(exclude_unset=False)

    # 7️⃣ Background task
    async def run_task(job_obj: SafeMigrationJob):
        try:
            await asyncio.sleep(3)  # simulate migration
            job_obj.status = "completed"
            job_obj.completed_at = datetime.now(timezone.utc)
            job_obj.logs.append("Migration finished successfully")
        except Exception as e:
            job_obj.status = "failed"
            job_obj.completed_at = datetime.now(timezone.utc)
            job_obj.errors.append(str(e))
        finally:
            for i, j in enumerate(migration_jobs_memory):
                if j["id"] == job_obj.id:
                    migration_jobs_memory[i] = job_obj.model_dump(exclude_unset=False)

    background_tasks.add_task(run_task, job)

    return {"message": "Migration started", "job_id": job_id}



@api_router.get("/migrations/{job_id}/progress")
async def get_migration_progress(job_id: str):
    """Get real-time migration progress"""
    if job_id in active_jobs:
        engine = active_jobs[job_id]
        return engine.get_progress()
    
    # If not active, get from database
    job = await db.migration_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found")
    
    return {
        "status": job.get("status"),
        "total_resources": job.get("total_resources", 0),
        "completed_resources": job.get("completed_resources", 0),
        "failed_resources": job.get("failed_resources", 0),
        "progress_percentage": (
            (job.get("completed_resources", 0) / job.get("total_resources", 1) * 100)
            if job.get("total_resources", 0) > 0 else 0
        ),
        "logs": job.get("logs", [])[-10:]
    }

@api_router.get("/migrations/{job_id}/logs")
async def get_migration_logs(job_id: str):
    """Get migration logs"""
    job = await db.migration_jobs.find_one({"id": job_id}, {"_id": 0})
    
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found")
    
    return {
        "logs": job.get("logs", []),
        "errors": job.get("errors", []),
        "warnings": job.get("warnings", [])
    }


# === Mock Data Routes ===

@api_router.get("/mock/edge-export")
async def get_mock_edge_export():
    """Get mock Edge export data for demo"""
    generator = MockDataGenerator()
    return generator.generate_complete_export()

@api_router.get("/edge/real-export")
async def get_real_edge_export():
    """Get real Edge export data from uploaded files"""
    from utils.edge_data_parser import EdgeDataParser
    parser = EdgeDataParser()
    return parser.parse_all()

@api_router.get("/edge/summary")
async def get_edge_summary():
    """Get summary of Edge resources"""
    from utils.edge_data_parser import EdgeDataParser
    parser = EdgeDataParser()
    return parser.get_summary()

@api_router.get("/edge/assessment")
async def get_edge_assessment():
    """Get migration assessment for Edge resources"""
    from utils.edge_data_parser import EdgeDataParser
    from migration.dependency_analyzer import DependencyAnalyzer
    
    parser = EdgeDataParser()
    edge_data = parser.parse_all()
    
    # Perform assessment
    assessor = MigrationAssessment()
    assessment = assessor.assess_all_resources(edge_data)
    
    # Add dependency analysis
    dep_analyzer = DependencyAnalyzer()
    dependencies = dep_analyzer.analyze_dependencies(edge_data)
    assessment["dependencies"] = dependencies
    assessment["migration_order"] = dep_analyzer.get_migration_order(dependencies)
    
    return assessment

 # === Unified Apigee Configuration Routes ===

@api_router.post(
    "/config/apigee",
    response_model=ApigeeConfigResponse,
    tags=["Configuration"],
    summary="Configure and verify Apigee connection",
    description="""
    Configure and verify connection to Apigee Edge or Apigee X.
    
    **Unified Payload Structure (for both Edge and X):**
    - `gateway_type`: "Edge" or "X" (required)
    - `organization`: Organization name (required)
    - `login_url`: Management API base URL (required)
    - `username`: Username for authentication (required)
    - `password`: Password for authentication (required for Edge, optional for X)
    - `accessToken`: Access token for authentication (alternative to password for X)
    - `environment`: Environment name (optional)
    
    **Backward Compatibility:**
    - Legacy fields are supported: `apigee_type`, `org_id`, `base_url`, `oauth_token`
    - These will be automatically mapped to unified fields
    
    The endpoint will:
    1. Validate the request payload
    2. Verify the connection by making a test API call
    3. Encrypt and store credentials securely in the database
    4. Return success response with configuration details
    
    **Security:**
    - Passwords and tokens are encrypted before storage
    - Only metadata is returned in responses (credentials are masked)
    """,
    responses={
        200: {
            "description": "Configuration verified and stored successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Apigee Edge configuration verified and stored successfully",
                        "apigee_type": "Edge",
                        "org_id": "my-org",
                        "environment": "prod",
                        "base_url": "https://api.enterprise.apigee.com",
                        "verified_at": "2024-01-01T00:00:00Z",
                        "stored": True
                    }
                }
            }
        },
        400: {
            "description": "Invalid request data",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Missing required field: org_id",
                        "error_code": "VALIDATION_ERROR"
                    }
                }
            }
        },
        401: {
            "description": "Authentication failed",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Authentication failed: Invalid credentials",
                        "error_code": "AUTH_ERROR"
                    }
                }
            }
        },
        503: {
            "description": "Service unavailable (network issues, API unreachable)",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Network error: Unable to reach https://api.enterprise.apigee.com",
                        "error_code": "NETWORK_ERROR"
                    }
                }
            }
        }
    }
)
async def save_apigee_config(config: ApigeeConfigRequest):
    """
    Save and verify Apigee configuration (Edge or X).
    
    This endpoint accepts a unified configuration format for both Apigee Edge and Apigee X.
    
    **Unified Payload Structure:**
    - gateway_type: "Edge" or "X" (required)
    - organization: Organization name (required)
    - login_url: Management API base URL (required)
    - username: Username for authentication (required)
    - password: Password for authentication (required for Edge, optional for X)
    - accessToken: Access token for authentication (alternative to password for X)
    - environment: Environment name (optional)
    
    **For Edge:**
    - Uses: organization, login_url, username, password
    
    **For X:**
    - Uses: organization, login_url, username, password OR accessToken
    
    Returns:
        - 200: Configuration verified and stored
        - 400: Invalid request (missing fields, validation errors)
        - 401: Authentication failed
        - 503: Service unavailable (network issues, API unreachable)
    """
    global _in_memory_config
    try:
        # Use gateway_type (with fallback to apigee_type for backward compatibility)
        gateway_type = config.gateway_type or config.apigee_type or "Edge"
        verified_at = datetime.now(timezone.utc)
        
        # Map unified fields with backward compatibility
        organization = config.organization or config.org_id
        login_url = config.login_url or config.base_url
        username = config.username
        password = config.password
        access_token = config.accessToken or config.oauth_token
        environment = config.environment
        
        # Validate required unified fields
        if not organization:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: organization (or org_id for Edge)"
            )
        if not login_url:
            # Set defaults based on gateway type
            if gateway_type == "Edge":
                login_url = "https://api.enterprise.apigee.com"
            else:
                login_url = "https://apigee.googleapis.com"
        if not username:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: username"
            )
        
        # Validate authentication - must have either password or accessToken
        if not password and not access_token:
            raise HTTPException(
                status_code=400,
                detail="Either 'password' or 'accessToken' must be provided"
            )
        
        # Validate and verify Edge configuration
        if gateway_type == "Edge":
            # Edge requires password (not accessToken)
            if not password:
                raise HTTPException(
                    status_code=400,
                    detail="Missing required field: password (required for Edge)"
                )
            
            # Default login URL for Edge if not provided
            if not login_url:
                login_url = "https://api.enterprise.apigee.com"
            
            # Verify connection (if enabled)
            # TODO: Enable real verification when Apigee credentials are available
            # Set ENABLE_APIGEE_VERIFICATION=true environment variable to enable
            if ENABLE_APIGEE_VERIFICATION:
                try:
                    edge_client = ApigeeEdgeClient(
                        org=organization,
                        username=username,
                        password=password,
                        base_url=login_url
                    )
                    success, message = edge_client.verify_connection()
                    
                    if not success:
                        # Determine appropriate error code
                        if "Authentication failed" in message or "Invalid credentials" in message:
                            error_code = 401
                        elif "Network error" in message or "timeout" in message.lower():
                            error_code = 503
                        else:
                            error_code = 400
                        
                        raise HTTPException(
                            status_code=error_code,
                            detail=message
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Edge verification error: {str(e)}")
                    raise HTTPException(
                        status_code=503,
                        detail=f"Connection verification failed: {str(e)}"
                    )
            else:
                # Verification disabled - assume success for development/testing
                logger.info(f"Apigee Edge verification skipped (ENABLE_APIGEE_VERIFICATION=false). Storing configuration for org: {organization}")
            
            # Prepare config document for storage (using unified fields only)
            config_doc = {
                "gateway_type": "Edge",
                "organization": organization,
                "login_url": login_url,
                "environment": environment,
                "username": username,
                # Encrypt password before storing
                "password_encrypted": encrypt_credential(password),
                "created_at": verified_at.isoformat(),
                "verified": ENABLE_APIGEE_VERIFICATION,  # True if actually verified, False if skipped
                "verified_at": verified_at.isoformat(),
                "verification_skipped": not ENABLE_APIGEE_VERIFICATION  # Flag to indicate if verification was skipped
            }
            
            # Add legacy fields only if they were provided in the request (for backward compatibility)
            if config.apigee_type:
                config_doc["apigee_type"] = "Edge"
            if config.org_id:
                config_doc["org_id"] = organization
            if config.base_url:
                config_doc["base_url"] = login_url
            
            # Store in Firestore (only for this endpoint)
            stored_in_firestore = False
            if firestore_db is not None:
                try:
                    # Remove old Edge configs
                    configs_ref = firestore_db.collection('apigee_configs')
                    old_configs = configs_ref.where('gateway_type', '==', 'Edge').stream()
                    for doc in old_configs:
                        doc.reference.delete()
                    
                    # Insert new config
                    configs_ref.add(config_doc)
                    stored_in_firestore = True
                    logger.info(f"Successfully stored Edge config in Firestore")
                except Exception as e:
                    logger.error(f"Failed to store in Firestore: {str(e)}")
                    logger.exception(e)
                    # Fallback to memory storage
                    _in_memory_config = config_doc
            else:
                # Store in memory (not recommended for production)
                logger.warning("Firestore not available - storing Edge config in memory")
                _in_memory_config = config_doc
            
            # Determine message based on verification status
            if ENABLE_APIGEE_VERIFICATION:
                message = "Apigee Edge configuration verified and stored successfully"
            else:
                message = "Apigee Edge configuration stored successfully (verification skipped)"
            
            return ApigeeConfigResponse(
                success=True,
                message=message,
                apigee_type="Edge",
                org_id=organization,
                organization=organization,
                environment=environment,
                base_url=login_url,
                verified_at=verified_at,
                stored=stored_in_firestore
            )
        
        # Validate and verify X configuration
        elif gateway_type == "X":
            # X can use either password or accessToken
            # Default login URL for X if not provided
            if not login_url:
                login_url = "https://apigee.googleapis.com"
            
            # For X, prefer accessToken over password if both provided
            auth_token = access_token or password
            
            if not auth_token:
                raise HTTPException(
                    status_code=400,
                    detail="Either 'password' or 'accessToken' must be provided for X"
                )
            
            # Verify connection (if enabled)
            if ENABLE_APIGEE_VERIFICATION:
                try:
                    # Verify using access token (or password as token) - make direct API call
                    import requests as req_lib
                    test_url = f"{login_url}/v1/organizations/{organization}/apis"
                    headers = {"Authorization": f"Bearer {auth_token}"}
                    
                    try:
                        response = req_lib.get(test_url, headers=headers, timeout=10)
                        if response.status_code == 200:
                            # Success
                            pass
                        elif response.status_code == 401:
                            raise HTTPException(
                                status_code=401,
                                detail="Authentication failed: Invalid access token or password"
                            )
                        elif response.status_code == 403:
                            raise HTTPException(
                                status_code=401,
                                detail="Authorization failed: Insufficient permissions"
                            )
                        elif response.status_code == 404:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Organization '{organization}' not found"
                            )
                        else:
                            raise HTTPException(
                                status_code=503,
                                detail=f"API request failed: HTTP {response.status_code}"
                            )
                    except req_lib.exceptions.ConnectionError:
                        raise HTTPException(
                            status_code=503,
                            detail=f"Network error: Unable to reach {login_url}"
                        )
                    except req_lib.exceptions.Timeout:
                        raise HTTPException(
                            status_code=503,
                            detail=f"Connection timeout: {login_url} did not respond"
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"X verification error: {str(e)}")
                    raise HTTPException(
                        status_code=503,
                        detail=f"Connection verification failed: {str(e)}"
                    )
            else:
                # Verification disabled - assume success for development/testing
                logger.info(f"Apigee X verification skipped (ENABLE_APIGEE_VERIFICATION=false). Storing configuration for org: {organization}")
            
            # Prepare config document for storage (using unified fields only)
            config_doc = {
                "gateway_type": "X",
                "organization": organization,
                "login_url": login_url,
                "environment": environment,
                "username": username,
                "created_at": verified_at.isoformat(),
                "verified": ENABLE_APIGEE_VERIFICATION,
                "verified_at": verified_at.isoformat(),
                "verification_skipped": not ENABLE_APIGEE_VERIFICATION
            }
            
            # Encrypt and store credentials - only store what was actually provided
            # Prefer accessToken over password if both are provided
            if access_token:
                config_doc["accessToken_encrypted"] = encrypt_credential(access_token)
            elif password:
                # Only store password if accessToken was not provided
                config_doc["password_encrypted"] = encrypt_credential(password)
            
            # Add legacy fields only if they were explicitly provided in the request (for backward compatibility)
            # Don't duplicate - only add if the legacy field was in the original request
            if config.apigee_type and config.apigee_type != gateway_type:
                config_doc["apigee_type"] = "X"
            if config.base_url and config.base_url != login_url:
                config_doc["base_url"] = config.base_url
            # Only store oauth_token_encrypted if oauth_token was explicitly provided (not mapped from accessToken)
            if config.oauth_token and (not access_token or config.oauth_token != access_token):
                config_doc["oauth_token_encrypted"] = encrypt_credential(config.oauth_token)
            if config.project_id:
                config_doc["project_id"] = config.project_id
            
            # Store in Firestore (only for this endpoint)
            stored_in_firestore = False
            if firestore_db is not None:
                try:
                    # Remove old X configs
                    configs_ref = firestore_db.collection('apigee_configs')
                    old_configs = configs_ref.where('gateway_type', '==', 'X').stream()
                    for doc in old_configs:
                        doc.reference.delete()
                    
                    # Insert new config
                    configs_ref.add(config_doc)
                    stored_in_firestore = True
                    logger.info(f"Successfully stored X config in Firestore")
                except Exception as e:
                    logger.error(f"Failed to store in Firestore: {str(e)}")
                    logger.exception(e)
                    # Fallback to memory storage
                    _in_memory_config = config_doc
            else:
                # Store in memory
                logger.warning("Firestore not available - storing X config in memory")
                _in_memory_config = config_doc
            
            # Determine message based on verification status
            if ENABLE_APIGEE_VERIFICATION:
                message = "Apigee X configuration verified and stored successfully"
            else:
                message = "Apigee X configuration stored successfully (verification skipped)"
            
            return ApigeeConfigResponse(
                success=True,
                message=message,
                apigee_type="X",
                organization=organization,
                project_id=config.project_id if hasattr(config, 'project_id') else None,
                environment=environment,
                base_url=login_url,
                verified_at=verified_at,
                stored=stored_in_firestore
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gateway_type: {gateway_type}. Must be 'Edge' or 'X'"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save config: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@api_router.get("/config/environment")
async def get_environment_variables():
    """
    Get list of all environment variables needed for the application and their current values.
    
    Returns:
        Dictionary containing environment variables with their descriptions, current values (masked if sensitive), and status.
    """
    import os
    from pathlib import Path
    
    # Define all environment variables used by the application
    env_vars = {
        "ENABLE_APIGEE_VERIFICATION": {
            "description": "Enable real Apigee connection verification. Set to 'true', '1', or 'yes' to enable verification.",
            "required": False,
            "sensitive": False,
            "default": "false",
            "current_value": os.environ.get("ENABLE_APIGEE_VERIFICATION", "false"),
            "is_set": "ENABLE_APIGEE_VERIFICATION" in os.environ,
            "effective_value": str(ENABLE_APIGEE_VERIFICATION)
        },
        "MONGO_URL": {
            "description": "MongoDB connection string. Set to 'none', 'no', 'false', '0', or empty to disable MongoDB.",
            "required": False,
            "sensitive": True,
            "default": "none (MongoDB disabled)",
            "current_value": "***MASKED***" if os.environ.get("MONGO_URL") else None,
            "is_set": "MONGO_URL" in os.environ and os.environ.get("MONGO_URL", "").strip().lower() not in ["none", "no", "false", "0", ""],
            "effective_value": "disabled" if mongo_url in ["none", "no", "false", "0", ""] else "enabled"
        },
        "DB_NAME": {
            "description": "MongoDB database name (only used if MONGO_URL is set).",
            "required": False,
            "sensitive": False,
            "default": "apigee_migration",
            "current_value": os.environ.get("DB_NAME", "apigee_migration"),
            "is_set": "DB_NAME" in os.environ,
            "effective_value": os.environ.get("DB_NAME", "apigee_migration")
        },
        "FIRESTORE_CREDENTIALS": {
            "description": "Path to Firestore credentials JSON file.",
            "required": False,
            "sensitive": False,
            "default": "credentials/firestore-credentials.json",
            "current_value": os.environ.get("FIRESTORE_CREDENTIALS", str(ROOT_DIR / "credentials" / "firestore-credentials.json")),
            "is_set": "FIRESTORE_CREDENTIALS" in os.environ,
            "effective_value": os.environ.get("FIRESTORE_CREDENTIALS", str(ROOT_DIR / "credentials" / "firestore-credentials.json")),
            "file_exists": os.path.exists(os.environ.get("FIRESTORE_CREDENTIALS", str(ROOT_DIR / "credentials" / "firestore-credentials.json")))
        },
        "FIRESTORE_PROJECT_ID": {
            "description": "Google Cloud Project ID for Firestore (optional, will be inferred from credentials if not set).",
            "required": False,
            "sensitive": False,
            "default": None,
            "current_value": os.environ.get("FIRESTORE_PROJECT_ID", None),
            "is_set": "FIRESTORE_PROJECT_ID" in os.environ and os.environ.get("FIRESTORE_PROJECT_ID") is not None,
            "effective_value": os.environ.get("FIRESTORE_PROJECT_ID", "inferred from credentials")
        },
        "CORS_ORIGINS": {
            "description": "Comma-separated list of allowed CORS origins. Use '*' for all origins.",
            "required": False,
            "sensitive": False,
            "default": "*",
            "current_value": os.environ.get("CORS_ORIGINS", "*"),
            "is_set": "CORS_ORIGINS" in os.environ,
            "effective_value": os.environ.get("CORS_ORIGINS", "*").split(",")
        },
        "PORT": {
            "description": "Server port number.",
            "required": False,
            "sensitive": False,
            "default": "8080",
            "current_value": os.environ.get("PORT", "8080"),
            "is_set": "PORT" in os.environ,
            "effective_value": int(os.environ.get("PORT", 8080))
        },
        "APIGEE_ENCRYPTION_KEY": {
            "description": "Encryption key for credential encryption (base64-encoded Fernet key). If not set, a default key is generated (NOT SECURE FOR PRODUCTION).",
            "required": False,
            "sensitive": True,
            "default": "Generated default key (NOT SECURE)",
            "current_value": "***MASKED***" if os.environ.get("APIGEE_ENCRYPTION_KEY") else None,
            "is_set": "APIGEE_ENCRYPTION_KEY" in os.environ and os.environ.get("APIGEE_ENCRYPTION_KEY") is not None,
            "effective_value": "set" if os.environ.get("APIGEE_ENCRYPTION_KEY") else "using default (NOT SECURE)"
        },
        "GOOGLE_APPLICATION_CREDENTIALS": {
            "description": "Path to Google Application Credentials JSON file (set automatically from FIRESTORE_CREDENTIALS).",
            "required": False,
            "sensitive": False,
            "default": "Set automatically from FIRESTORE_CREDENTIALS",
            "current_value": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", None),
            "is_set": "GOOGLE_APPLICATION_CREDENTIALS" in os.environ,
            "effective_value": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "not set")
        }
    }
    
    # Add connection status information
    connection_status = {
        "mongodb": {
            "enabled": client is not None and db is not None,
            "status": "connected" if client is not None and db is not None else "disabled or unavailable"
        },
        "firestore": {
            "enabled": firestore_db is not None,
            "status": "connected" if firestore_db is not None else "disabled or unavailable",
            "available": FIRESTORE_AVAILABLE
        }
    }
    
    return {
        "environment_variables": env_vars,
        "connection_status": connection_status,
        "summary": {
            "total_variables": len(env_vars),
            "set_variables": sum(1 for v in env_vars.values() if v["is_set"]),
            "required_variables": sum(1 for v in env_vars.values() if v.get("required", False)),
            "sensitive_variables": sum(1 for v in env_vars.values() if v.get("sensitive", False))
        }
    }


@api_router.get("/config/apigee")
async def get_apigee_config(apigee_type: Optional[str] = None):
    """
    Get saved Apigee configuration (without sensitive credentials).
    
    Args:
        apigee_type: Optional filter by type ("Edge" or "X")
    
    Returns:
        Configuration details with masked credentials
    """
    global _in_memory_config
    try:
        query = {}
        if apigee_type:
            query["apigee_type"] = apigee_type
        
        # Use Firestore for this endpoint (not MongoDB)
        if firestore_db is not None:
            configs = []
            configs_ref = firestore_db.collection('apigee_configs')
            if apigee_type:
                # Try gateway_type first, then fallback to apigee_type for backward compatibility
                docs = list(configs_ref.where('gateway_type', '==', apigee_type).stream())
                if not docs:
                    docs = list(configs_ref.where('apigee_type', '==', apigee_type).stream())
            else:
                docs = list(configs_ref.stream())
            
            for doc in docs:
                config_data = doc.to_dict()
                configs.append(config_data)
        else:
            configs = [_in_memory_config] if _in_memory_config and (
                not apigee_type or _in_memory_config.get("apigee_type") == apigee_type
            ) else []
        
        if not configs:
            return {"configured": False}
        
        # Return safe configs (masked credentials) - using unified fields
        safe_configs = []
        for config_item in configs:
            gateway_type = config_item.get("gateway_type") or config_item.get("apigee_type", "Edge")
            safe_config = {
                "configured": True,
                "gateway_type": gateway_type,
                "organization": config_item.get("organization") or config_item.get("org_id"),
                "login_url": config_item.get("login_url") or config_item.get("base_url"),
                "username": config_item.get("username"),
                "environment": config_item.get("environment"),
                "verified": config_item.get("verified", False),
                "verified_at": config_item.get("verified_at"),
                "created_at": config_item.get("created_at")
            }
            
            # Add backward compatibility fields in response only if they exist in DB
            if config_item.get("apigee_type"):
                safe_config["apigee_type"] = config_item.get("apigee_type")
            if config_item.get("base_url"):
                safe_config["base_url"] = config_item.get("base_url")
            
            # Mask credentials - check unified field first, then legacy
            if config_item.get("accessToken_encrypted"):
                safe_config["accessToken_masked"] = mask_credential(config_item.get("accessToken_encrypted", ""), 0)
            elif config_item.get("oauth_token_encrypted"):
                safe_config["accessToken_masked"] = mask_credential(config_item.get("oauth_token_encrypted", ""), 0)
            
            if config_item.get("password_encrypted"):
                safe_config["password_masked"] = mask_credential(config_item.get("password_encrypted", ""), 0)
            
            # Backward compatibility fields in response
            if gateway_type == "Edge" and config_item.get("org_id"):
                safe_config["org_id"] = config_item.get("org_id")
            elif gateway_type == "X" and config_item.get("project_id"):
                safe_config["project_id"] = config_item.get("project_id")
            
            safe_configs.append(safe_config)
        
        return {
            "configs": safe_configs,
            "count": len(safe_configs)
        }
    except Exception as e:
        logger.error(f"Failed to get config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# === Apigee X Configuration Routes ===

@api_router.post("/config/apigee-x")
async def save_apigee_x_config(config: Dict[str, Any]):
    """Save Apigee X configuration"""
    try:
        # Validate required fields
        required_fields = ["apigeex_org_name", "apigeex_token", "apigeex_env"]
        for field in required_fields:
            if not config.get(field):
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Add default management URL if not provided
        if "apigeex_mgmt_url" not in config:
            config["apigeex_mgmt_url"] = "https://apigee.googleapis.com/v1/organizations/"
        
        # Add folder name
        base_dir = os.path.dirname(os.path.abspath(__file__))  # current script directory
        default_folder = os.path.join(base_dir, "backend", "data_edge")
        
        # Use provided folder_name or fallback to default
        folder_name = config.get("folder_name", default_folder)
        folder_name = os.path.abspath(folder_name)  # ensure absolute path
        config["folder_name"] = folder_name
        
        # Verify credentials
        migrator = ApigeeXMigrator(config)
        success, message = migrator.verify_credentials()
        
        if not success:
            raise HTTPException(status_code=401, detail=message)
        
        # Save to database if available
        if db is not None:
            await db.apigee_x_config.delete_many({})  # Remove old configs
            config_doc = {
                **config,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "verified": True
            }
            await db.apigee_x_config.insert_one(config_doc)
        else:
            # Store in memory if no database
            global _in_memory_config
            _in_memory_config = config
        
        return {
            "success": True,
            "message": "Configuration saved and verified successfully",
            "config": {
                "org_name": config["apigeex_org_name"],
                "env": config["apigeex_env"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/config/apigee-x")
async def get_apigee_x_config():
    """Get saved Apigee X configuration (without sensitive token)"""
    global _in_memory_config
    if db is not None:
        config = await db.apigee_x_config.find_one({}, {"_id": 0})
    else:
        config = _in_memory_config
    
    if not config:
        return {"configured": False}
    
    # Remove sensitive information
    safe_config = {
        "configured": True,
        "org_name": config.get("apigeex_org_name"),
        "env": config.get("apigeex_env"),
        "mgmt_url": config.get("apigeex_mgmt_url"),
        "token_preview": config.get("apigeex_token", "")[:10] + "..." if config.get("apigeex_token") else None
    }
    
    return safe_config

@api_router.post("/config/verify")
async def verify_apigee_x_credentials(config: Dict[str, Any]):
    """Verify Apigee X credentials without saving"""
    try:
        if "apigeex_mgmt_url" not in config:
            config["apigeex_mgmt_url"] = "https://apigee.googleapis.com/v1/organizations/"
        base_dir = os.path.dirname(os.path.abspath(__file__))  # current script directory
        default_folder = os.path.join(base_dir, "backend", "data_edge")
        
        # Use provided folder_name or fallback to default
        folder_name = config.get("folder_name", default_folder)
        folder_name = os.path.abspath(folder_name)  # ensure absolute path
        config["folder_name"] = folder_name
        
        migrator = ApigeeXMigrator(config)
        success, message = migrator.verify_credentials()
        
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

# === Discovery Routes ===

@api_router.get("/discover/real")
async def discover_real_resources():
    """Discover all resources from the Edge data folder"""
    from utils.edge_data_parser import EdgeDataParser
    
    try:
        parser = EdgeDataParser()
        resources = parser.parse_all()
        
        return {
            "success": True,
            "resources": resources,
            "summary": parser.get_summary()
        }
    except Exception as e:
        logger.error(f"Discovery failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/assess")
async def assess_resources():
    """Perform migration assessment with dependency analysis"""
    from utils.edge_data_parser import EdgeDataParser
    from migration.dependency_analyzer import DependencyAnalyzer
    
    try:
        parser = EdgeDataParser()
        edge_data = parser.parse_all()
        
        # Perform assessment
        assessor = MigrationAssessment()
        assessment = assessor.assess_all_resources(edge_data)
        
        # Add dependency analysis
        dep_analyzer = DependencyAnalyzer()
        dependencies = dep_analyzer.analyze_dependencies(edge_data)
        assessment["dependencies"] = dependencies
        assessment["migration_order"] = dep_analyzer.get_migration_order(dependencies)
        
        return {
            "success": True,
            "assessment": assessment
        }
    except Exception as e:
        logger.error(f"Assessment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/dependencies")
async def get_dependencies():
    """Get dependency graph for all resources"""
    from utils.edge_data_parser import EdgeDataParser
    from migration.dependency_analyzer import DependencyAnalyzer
    
    try:
        parser = EdgeDataParser()
        edge_data = parser.parse_all()
        
        dep_analyzer = DependencyAnalyzer()
        dependencies = dep_analyzer.analyze_dependencies(edge_data)
        migration_order = dep_analyzer.get_migration_order(dependencies)
        
        return {
            "success": True,
            "dependencies": dependencies,
            "migration_order": migration_order
        }
    except Exception as e:
        logger.error(f"Dependency analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# === Real Migration Routes ===

@api_router.post("/migrate/resource")
async def migrate_single_resource(payload: Dict[str, Any]):
    """
    Migrate a single resource (stubbed implementation).

    TODO: Enable real Apigee migration once credentials are available.
    Currently returns stubbed success response and stores migration status in Firestore.
    """
    try:
        # ======================================================
        # 1. VALIDATE REQUIRED FIELDS
        # ======================================================
        resource_type = payload.get("resource_type")
        resource_name = payload.get("resource_name")
        
        if not resource_type or not resource_name:
            raise HTTPException(
                status_code=400, 
                detail="resource_type and resource_name are required"
                )

        # Normalize resource type
        normalize_map = {
            "target_server": "targetserver",
            "targetserver": "targetserver",
            "proxy": "proxy",
            "shared_flow": "sharedflow",
            "sharedflow": "sharedflow",
            "kvm": "kvm",
            "api_product": "apiproduct",
            "apiproduct": "apiproduct",
            "developer": "developer",
            "app": "app"
        }

        normalized_type = normalize_map.get(resource_type.lower(), resource_type.lower())
        
        # Get gateway type from payload or config (default to "X" for migration)
        gateway_type = payload.get("gateway_type") or payload.get("apigee_type") or "X"
        
        # Clean resource name (remove .zip extension if present)
        clean_resource_name = resource_name.replace(".zip", "")
        
        # ======================================================
        # 2. STUBBED MIGRATION LOGIC
        # ======================================================
        # TODO: Enable real Apigee migration once credentials are available
        # TODO: Replace this stubbed logic with actual Apigee Edge to X migration
        # TODO: Use ApigeeXMigrator or similar to perform real migration
        
        logger.info(f"Stubbed migration: {normalized_type} '{clean_resource_name}' (gateway_type: {gateway_type})")
        
        # Assume migration is successful (stubbed)
        migration_status = "migrated"
        migration_timestamp = datetime.now(timezone.utc)
        
        # ======================================================
        # 3. GENERATE UNIQUE IDENTIFIER
        # ======================================================
        # Unique identifier: combination of gateway_type, resource_type, and resource_name
        unique_id = f"{gateway_type}_{normalized_type}_{clean_resource_name}"
        
        # ======================================================
        # 4. PREPARE METADATA
        # ======================================================
        metadata = {
            "resource_type": normalized_type,
            "original_resource_name": resource_name,
            "scope": payload.get("scope", "env"),
            "environment": payload.get("environment"),
            "source_org": payload.get("source_org"),
            "target_org": payload.get("target_org"),
            "policy_count": payload.get("policy_count", 0),
            "warnings": payload.get("warnings", []),
            "readiness": payload.get("readiness", "ready")
        }
        
        # ======================================================
        # 5. STORE MIGRATION STATUS IN FIRESTORE
        # ======================================================
        migration_doc = {
            "unique_id": unique_id,
            "proxy_name": clean_resource_name,  # Using proxy_name for UI compatibility (works for all resource types)
            "resource_type": normalized_type,
            "resource_name": clean_resource_name,
            "gateway_type": gateway_type,
            "apigee_type": gateway_type,  # Backward compatibility
            "status": migration_status,
            "verification_mode": "stub",
            "migrated_at": migration_timestamp.isoformat(),
            "created_at": migration_timestamp.isoformat(),
            "metadata": metadata
        }
        
        stored_in_firestore = False
        if firestore_db is not None:
            try:
                migrations_ref = firestore_db.collection('migrations')
                # Check if migration already exists
                existing_docs = list(migrations_ref.where('unique_id', '==', unique_id).stream())
                
                if existing_docs:
                    # Update existing migration
                    for doc in existing_docs:
                        doc.reference.update(migration_doc)
                    logger.info(f"Updated existing migration record: {unique_id}")
                else:
                    # Create new migration record
                    migrations_ref.add(migration_doc)
                    logger.info(f"Stored migration record in Firestore: {unique_id}")
                
                stored_in_firestore = True
            except Exception as e:
                logger.error(f"Failed to store migration in Firestore: {str(e)}")
                logger.exception(e)
        else:
            logger.warning("Firestore not available - migration status not persisted")
        
        # ======================================================
        # 6. RETURN STUBBED SUCCESS RESPONSE
        # ======================================================
        response = {
            "proxy_name": clean_resource_name,
            "status": migration_status,
            "verification_mode": "stub",
            "unique_id": unique_id,
            "resource_type": normalized_type,
            "gateway_type": gateway_type,
            "migrated_at": migration_timestamp.isoformat(),
            "stored": stored_in_firestore
        }
        
        # Add metadata for UI display
        if metadata.get("policy_count") is not None:
            response["policy_count"] = metadata["policy_count"]
        if metadata.get("warnings"):
            response["warnings"] = metadata["warnings"]
        if metadata.get("readiness"):
            response["readiness"] = metadata["readiness"]
        
        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Migration failed: {str(e)}"
        )


@api_router.get("/migrate/status")
async def get_migration_status(
    proxy_name: Optional[str] = None,
    resource_type: Optional[str] = None,
    gateway_type: Optional[str] = None,
    unique_id: Optional[str] = None
):
    """
    Get migration status for resources.
    
    Query Parameters:
    - proxy_name: Filter by proxy/resource name
    - resource_type: Filter by resource type (proxy, sharedflow, etc.)
    - gateway_type: Filter by gateway type (Edge or X)
    - unique_id: Get specific migration by unique ID
    
    Returns migration status including proxy name, status, and metadata.
    """
    try:
        migrations = []
        
        if firestore_db is not None:
            try:
                migrations_ref = firestore_db.collection('migrations')
                
                # Build query based on filters
                if unique_id:
                    # Get specific migration by unique_id
                    docs = list(migrations_ref.where('unique_id', '==', unique_id).stream())
                elif proxy_name:
                    # Filter by proxy_name
                    docs = list(migrations_ref.where('proxy_name', '==', proxy_name).stream())
                    # Also filter by resource_name for backward compatibility
                    docs.extend(list(migrations_ref.where('resource_name', '==', proxy_name).stream()))
                else:
                    # Get all migrations, then filter
                    docs = list(migrations_ref.stream())
                
                # Apply additional filters
                for doc in docs:
                    data = doc.to_dict()
                    
                    # Apply filters
                    if resource_type and data.get("resource_type") != resource_type:
                        continue
                    if gateway_type and data.get("gateway_type") != gateway_type and data.get("apigee_type") != gateway_type:
                        continue
                    
                    migrations.append({
                        "unique_id": data.get("unique_id"),
                        "proxy_name": data.get("proxy_name") or data.get("resource_name"),
                        "resource_type": data.get("resource_type"),
                        "resource_name": data.get("resource_name"),
                        "gateway_type": data.get("gateway_type") or data.get("apigee_type"),
                        "status": data.get("status"),
                        "verification_mode": data.get("verification_mode", "stub"),
                        "migrated_at": data.get("migrated_at"),
                        "created_at": data.get("created_at"),
                        "metadata": data.get("metadata", {})
                    })
                
            except Exception as e:
                logger.error(f"Failed to query Firestore: {str(e)}")
                logger.exception(e)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve migration status: {str(e)}"
                )
        else:
            logger.warning("Firestore not available - cannot retrieve migration status")
        return {
                "migrations": [],
                "message": "Firestore not available"
            }
        
        # If unique_id specified and not found
        if unique_id and not migrations:
            raise HTTPException(
                status_code=404,
                detail=f"Migration not found for unique_id: {unique_id}"
            )
        
        # If proxy_name specified and not found
        if proxy_name and not migrations:
            return {
                "migrations": [],
                "proxy_name": proxy_name,
                "status": "not_migrated",
                "message": f"No migration found for proxy: {proxy_name}"
            }
        
        # Return response
        if len(migrations) == 1:
            # Single migration - return directly
            return migrations[0]
        else:
            # Multiple migrations - return list
            return {
                "migrations": migrations,
                "count": len(migrations)
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to get migration status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve migration status: {str(e)}"
        )


@api_router.get("/mock/resources/{resource_type}")
async def get_mock_resources(resource_type: str):
    """Get mock resources of a specific type"""
    generator = MockDataGenerator()
    
    if resource_type == "proxies":
        return [p.model_dump() for p in generator.generate_proxies()]
    elif resource_type == "shared_flows":
        return [sf.model_dump() for sf in generator.generate_shared_flows()]
    elif resource_type == "target_servers":
        return [ts.model_dump() for ts in generator.generate_target_servers()]
    elif resource_type == "kvms":
        return [kvm.model_dump() for kvm in generator.generate_kvms()]
    elif resource_type == "api_products":
        return [ap.model_dump() for ap in generator.generate_api_products()]
    elif resource_type == "developers":
        return [d.model_dump() for d in generator.generate_developers()]
    elif resource_type == "developer_apps":
        return [da.model_dump() for da in generator.generate_developer_apps()]
    else:
        raise HTTPException(status_code=404, detail="Resource type not found")


# === Diff & Comparison Routes ===

@api_router.post("/diff/calculate")
async def calculate_diff(payload: Dict[str, Any]):
    """Calculate differences between Edge and X resources"""
    edge_resource = payload.get("edge_resource", {})
    x_resource = payload.get("x_resource", {})
    resource_type = payload.get("resource_type", "unknown")
    resource_name = payload.get("resource_name", "unknown")
    
    calculator = DiffCalculator()
    diff = calculator.calculate_diff(edge_resource, x_resource, resource_type, resource_name)
    
    return diff.model_dump()

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === Replace deprecated @app.on_event with lifespan ===
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if client:
        client.close()

app.router.lifespan_context = lifespan

# --- START SERVER ---
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,   # VERY IMPORTANT
        workers=1
    )