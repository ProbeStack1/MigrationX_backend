from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, Request, Response
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
from migration.migration_engine import MigrationEngine
from migration.assessment_engine import MigrationAssessment
from migration.apigee_x_migrator import ApigeeXMigrator
from migration.apigee_edge_client import ApigeeEdgeClient
from utils.diff_calculator import DiffCalculator
from utils.mock_data import MockDataGenerator
import json


# Configure CORS middleware BEFORE including routers
# This ensures CORS headers are applied to all routes
allowed_origins = os.environ.get('CORS_ORIGINS', '').strip()
if allowed_origins:
    # Split by comma and strip whitespace from each origin
    origins_list = [origin.strip() for origin in allowed_origins.split(',') if origin.strip()]
else:
    # Default allowed origins if CORS_ORIGINS is not set
    origins_list = [
        "https://probestack.io",
        "http://localhost:5173",
        "http://localhost:5174"
    ]

# Configure logging first (before using logger)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger_cors = logging.getLogger(__name__)
logger_cors.info(f"CORS configured with allowed origins: {origins_list}")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Apigee verification setting (disable for development when credentials not available)
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

# Firestore import (for /config/apigee-x endpoint)
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    firestore = None

# Firestore connection (for /config/apigee-x and /probestack/v1/auth/apigee endpoints)
firestore_db_x = None
firestore_error = None
if FIRESTORE_AVAILABLE:
    try:
        # Check for Firestore emulator (for local development)
        firestore_emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
        if firestore_emulator:
            print(f"✓ Using Firestore emulator at: {firestore_emulator}")
            firestore_db_x = firestore.Client()
        else:
            # Check for credentials file in local credentials folder
            credentials_path = None
            local_credentials = ROOT_DIR / "credentials" / "firestore-credentials.json"
            if local_credentials.exists():
                credentials_path = str(local_credentials.absolute())
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                print(f"✓ Found local Firestore credentials: {credentials_path}")
            
            # Also check if GOOGLE_APPLICATION_CREDENTIALS is already set
            if not credentials_path:
                credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                if credentials_path:
                    print(f"✓ Using Firestore credentials from environment: {credentials_path}")
            
            # Try to get project ID from environment, or from credentials file
            project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
            
            # If we have credentials file, try to read project ID from it
            if not project_id and credentials_path:
                try:
                    import json
                    with open(credentials_path, 'r') as f:
                        creds_data = json.load(f)
                        project_id = creds_data.get("project_id")
                        if project_id:
                            print(f"✓ Found project ID in credentials: {project_id}")
                except Exception as e:
                    print(f"⚠ Could not read project ID from credentials: {e}")
            
            if project_id:
                firestore_db_x = firestore.Client(project=project_id)
                print(f"✓ Firestore connected (project: {project_id})")
            else:
                # Try without project ID (will use default from GCP credentials)
                firestore_db_x = firestore.Client()
                print("✓ Firestore connected (using default project from credentials)")
        
        # Test the connection by trying to access a collection
        try:
            test_ref = firestore_db_x.collection('_test_connection')
            # Just verify we can access collections (don't actually write)
            list(test_ref.limit(1).stream())
            print("✓ Firestore connection verified")
        except Exception as test_e:
            print(f"⚠ Firestore connection test failed: {test_e}")
            print("⚠ Firestore may not be properly configured - writes may fail")
            firestore_error = str(test_e)
    except Exception as e:
        firestore_error = str(e)
        print(f"⚠ Firestore connection failed: {firestore_error}")
        print("⚠ Firestore will use in-memory storage")
        print("⚠ To enable Firestore, ensure one of the following:")
        print("   1. Place credentials in: credentials/firestore-credentials.json")
        print("   2. Set GOOGLE_APPLICATION_CREDENTIALS to path of service account JSON")
        print("   3. Set GCP_PROJECT_ID environment variable")
        print("   4. Use Firestore emulator: set FIRESTORE_EMULATOR_HOST=localhost:8080")
        print(f"   Error: {type(e).__name__}: {firestore_error}")
        firestore_db_x = None
else:
    print("⚠ google-cloud-firestore not installed - Firestore will use in-memory storage")

# Create the main app without a prefix
app = FastAPI(title="Apigee Edge to X Migration API")

# Add CORS middleware with explicit headers (required when allow_credentials=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Get logger (logging already configured above)
logger = logging.getLogger(__name__)

# Add explicit OPTIONS handler for all routes as a fallback
# This ensures preflight requests are handled even if middleware has issues
@app.options("/{full_path:path}")
async def options_handler(full_path: str, request: Request):
    """Handle OPTIONS requests for CORS preflight"""
    # Get origin from request
    origin = request.headers.get("Origin", "")

    # Check if origin is in allowed list
    if origin in origins_list:
        allow_origin = origin
    elif not origins_list:
        allow_origin = "*"
    else:
        # If origin not in list, don't allow (security)
        allow_origin = origins_list[0] if origins_list else "*"

    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": ["*"],
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, Origin, Access-Control-Request-Method, Access-Control-Request-Headers",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "3600",
        }
    )

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Include the router in the main app (after CORS middleware)
app.include_router(api_router)

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

# === Unified Apigee Configuration Routes (Edge and X) ===

@api_router.post("/config/apigee")
async def save_apigee_config(payload: Dict[str, Any]):
    """
    Save Apigee Edge or Apigee X configuration
    
    Supports both gateway types:
    - apigee-edge: Requires userName, password, organization, url, environment
    - apigee-x: Requires organization, environment, url, apigeeOauthToken
    """
    global _in_memory_config
    try:
        # Extract and validate gatewayType
        gateway_type = payload.get("gatewayType", "").lower()
        if gateway_type not in ["apigee-edge", "apigee-x"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gatewayType: {gateway_type}. Must be 'apigee-edge' or 'apigee-x'"
            )
        
        # Extract fields
        probestack_user_email = payload.get("probestackUserEmail")
        organization = payload.get("organization")
        url = payload.get("url")
        environment = payload.get("environment")
        user_name = payload.get("userName")
        password = payload.get("password")
        apigee_oauth_token = payload.get("apigeeOauthToken")
        
        # Validate based on gateway type
        if gateway_type == "apigee-edge":
            # Required fields for Edge
            required_fields = {
                "userName": user_name,
                "password": password,
                "organization": organization,
                "url": url,
                "environment": environment
            }
            for field_name, field_value in required_fields.items():
                if not field_value:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Missing required field for apigee-edge: {field_name}"
                    )
            
            # Set default URL if not provided
            if not url:
                url = "https://api.enterprise.apigee.com"
            
            # Verify Edge credentials (if enabled)
            # TODO: Enable real verification when Apigee Edge credentials are available
            # Set ENABLE_APIGEE_VERIFICATION=true environment variable to enable
            if ENABLE_APIGEE_VERIFICATION:
                try:
                    edge_client = ApigeeEdgeClient(
                        org=organization,
                        username=user_name,
                        password=password,
                        base_url=url
                    )
                    # Test connection by getting organization info
                    status_code, response = edge_client._make_request("GET", "")
                    if status_code != 200:
                        raise HTTPException(
                            status_code=401,
                            detail=f"Authentication failed: {response.get('error', 'Invalid credentials')}"
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Edge verification error: {str(e)}")
                    raise HTTPException(
                        status_code=401,
                        detail=f"Connection verification failed: {str(e)}"
                    )
            else:
                # Verification disabled - assume success for development/testing
                logger.info(f"Apigee Edge verification skipped (ENABLE_APIGEE_VERIFICATION=false). Storing configuration for org: {organization}")
        
        elif gateway_type == "apigee-x":
            # Required fields for X
            required_fields = {
                "organization": organization,
                "environment": environment,
                "url": url,
                "apigeeOauthToken": apigee_oauth_token
            }
            for field_name, field_value in required_fields.items():
                if not field_value:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Missing required field for apigee-x: {field_name}"
                    )
            
            # Set default URL if not provided
            if not url:
                url = "https://apigee.googleapis.com/v1/organizations/"
            
            # Verify X credentials (if enabled)
            # TODO: Enable real verification when Apigee X credentials are available
            # Set ENABLE_APIGEE_VERIFICATION=true environment variable to enable
            if ENABLE_APIGEE_VERIFICATION:
                try:
                    # Create config dict for ApigeeXMigrator
                    x_config = {
                        "apigeex_org_name": organization,
                        "apigeex_token": apigee_oauth_token,
                        "apigeex_env": environment,
                        "apigeex_mgmt_url": url
                    }
                    migrator = ApigeeXMigrator(x_config)
                    success, message = migrator.verify_credentials()
                    
                    if not success:
                        raise HTTPException(status_code=401, detail=message)
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"X verification error: {str(e)}")
                    raise HTTPException(
                        status_code=401,
                        detail=f"Connection verification failed: {str(e)}"
                    )
            else:
                # Verification disabled - assume success for development/testing
                logger.info(f"Apigee X verification skipped (ENABLE_APIGEE_VERIFICATION=false). Storing configuration for org: {organization}")
        
        # Check for duplicate configuration before storing
        # Unique combination: gatewayType + probestackUserEmail + organization + environment + url
        duplicate_found = False
        existing_config = None
        existing_config_doc_id = None
        
        if firestore_db_x is not None:
            try:
                configs_ref = firestore_db_x.collection('apigee_configs')
                # Query for existing config with same unique combination
                query = configs_ref.where('gatewayType', '==', gateway_type) \
                                  .where('probestackUserEmail', '==', probestack_user_email) \
                                  .where('organization', '==', organization) \
                                  .where('environment', '==', environment) \
                                  .where('url', '==', url)
                
                existing_docs = list(query.stream())
                if existing_docs:
                    duplicate_found = True
                    existing_doc = existing_docs[0]
                    existing_config = existing_doc.to_dict()
                    existing_config_doc_id = existing_doc.id
                    logger.info(f"Duplicate configuration found: gatewayType={gateway_type}, org={organization}, env={environment}, user={probestack_user_email}")
            except Exception as e:
                logger.warning(f"Could not check for duplicates in Firestore: {e}. Proceeding with storage.")
        else:
            # Check in-memory storage if Firestore not available
            if _in_memory_config and isinstance(_in_memory_config, dict):
                if (_in_memory_config.get("gatewayType") == gateway_type and
                    _in_memory_config.get("probestackUserEmail") == probestack_user_email and
                    _in_memory_config.get("organization") == organization and
                    _in_memory_config.get("environment") == environment and
                    _in_memory_config.get("url") == url):
                    duplicate_found = True
                    existing_config = _in_memory_config
                    logger.info(f"Duplicate configuration found in memory storage")
        
        # If duplicate found, return existing configuration
        if duplicate_found and existing_config:
            # Simplified response structure
            response = {
                "success": True,
                "message": "Configuration already exists in database. Returning existing configuration.",
                "verified": existing_config.get("verified", False)
            }
            
            if existing_config_doc_id:
                response["firestore_doc_id"] = existing_config_doc_id
            
            # Since we found it in Firestore, mark as existing_fetched
            if firestore_db_x is not None and existing_config_doc_id:
                response["firestore_status"] = "existing_fetched"
            
            return response
        
        # Generate unique config ID if not provided
        config_id = payload.get("config_id") or str(uuid.uuid4())
        config_name = payload.get("config_name")
        if not config_name:
            if gateway_type == "apigee-edge":
                config_name = f"{organization}-{environment}"
            else:
                config_name = f"{organization}-{environment}"
        
        # Determine verification status based on gateway type
        # Both Edge and X use the same ENABLE_APIGEE_VERIFICATION flag
        verified = ENABLE_APIGEE_VERIFICATION
        
        # Prepare config document for storage
        config_doc = {
            "gatewayType": gateway_type,
            "probestackUserEmail": probestack_user_email,
            "organization": organization,
            "url": url,
            "environment": environment,
            "config_id": config_id,
            "config_name": config_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "verified": verified,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "verification_skipped": not verified  # Flag to indicate if verification was skipped
        }
        
        # Add gateway-specific fields
        if gateway_type == "apigee-edge":
            config_doc["userName"] = user_name
            # Encrypt password before storing
            try:
                from utils.credential_encryption import encrypt_credential
                config_doc["password_encrypted"] = encrypt_credential(password)
            except ImportError:
                logger.warning("credential_encryption module not available - storing password unencrypted")
                config_doc["password"] = password
            except Exception as e:
                logger.error(f"Encryption failed: {str(e)} - storing password unencrypted")
                config_doc["password"] = password
        elif gateway_type == "apigee-x":
            # Encrypt OAuth token before storing
            try:
                from utils.credential_encryption import encrypt_credential
                config_doc["apigeeOauthToken_encrypted"] = encrypt_credential(apigee_oauth_token)
            except ImportError:
                logger.warning("credential_encryption module not available - storing token unencrypted")
                config_doc["apigeeOauthToken"] = apigee_oauth_token
            except Exception as e:
                logger.error(f"Encryption failed: {str(e)} - storing token unencrypted")
                config_doc["apigeeOauthToken"] = apigee_oauth_token
        
        # Store in Firestore - supports multiple configs
        stored_in_firestore = False
        config_doc_id = None
        storage_error = None
        
        if firestore_db_x is not None:
            try:
                configs_ref = firestore_db_x.collection('apigee_configs')
                logger.info(f"Attempting to store config in Firestore collection 'apigee_configs' with config_id: {config_id}")
                
                # Check if config with same ID exists (update) or create new
                existing_docs = list(configs_ref.where('config_id', '==', config_id).stream())
                if existing_docs:
                    # Update existing config
                    doc_ref = existing_docs[0].reference
                    doc_ref.set(config_doc)
                    config_doc_id = doc_ref.id
                    logger.info(f"✓ Updated existing Apigee config in Firestore: {config_id} (doc_id: {config_doc_id})")
                else:
                    # Insert new config - Firestore add() returns (timestamp, DocumentReference)
                    result = configs_ref.add(config_doc)
                    if isinstance(result, tuple) and len(result) >= 2:
                        # Firestore add() returns (timestamp, DocumentReference)
                        doc_ref = result[1]
                        config_doc_id = doc_ref.id
                    elif hasattr(result, 'id'):
                        # If it's just a DocumentReference
                        config_doc_id = result.id
                    else:
                        # Fallback: try to get ID from result
                        config_doc_id = getattr(result, 'id', None)
                    
                    logger.info(f"✓ Successfully stored new Apigee config in Firestore: {config_id} (doc_id: {config_doc_id})")
                    
                    # Verify the write by reading it back
                    if config_doc_id:
                        try:
                            verify_doc = configs_ref.document(config_doc_id).get()
                            if verify_doc.exists:
                                logger.info(f"✓ Verified: Config document exists in Firestore")
                            else:
                                logger.warning(f"⚠ Warning: Config document not found after write (may need a moment to propagate)")
                        except Exception as verify_e:
                            logger.warning(f"⚠ Could not verify Firestore write: {verify_e}")
                
                stored_in_firestore = True
                logger.info(f"Config stored successfully. Firestore doc ID: {config_doc_id}")
            except Exception as e:
                storage_error = str(e)
                logger.error(f"✗ Failed to store in Firestore: {storage_error}")
                logger.exception(e)
                # Fallback to memory storage
                logger.warning("Falling back to in-memory storage due to Firestore error")
                _in_memory_config = config_doc
        else:
            # Store in memory (not recommended for production)
            logger.warning("Firestore not available - storing Apigee config in memory")
            storage_error = "Firestore client not initialized"
            _in_memory_config = config_doc
        
        # Determine message based on verification status
        if verified:
            message = f"Apigee {gateway_type} configuration saved and verified successfully"
        else:
            message = f"Apigee {gateway_type} configuration saved successfully (verification skipped)"
        
        # Simplified response structure
        response = {
            "success": True,
            "message": message,
            "verified": verified
        }
        
        if config_doc_id:
            response["firestore_doc_id"] = config_doc_id
        
        # Add Firestore status to response
        if not stored_in_firestore:
            if firestore_db_x is None:
                response["firestore_status"] = "not_available"
            else:
                response["firestore_status"] = "write_failed"
        else:
            response["firestore_status"] = "stored"
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/config/apigee/users/{user_id}")
async def get_user_apigee_configs(user_id: str, payload: Dict[str, Any]):
    """
    Get all Apigee configurations for a specific user email
    
    Path Parameters:
    - user_id: The user email to fetch configurations for (used as userEmail in query)
    
    Request Body:
    - gatewayType: "apigee-edge" or "apigee-x" (required)
    
    Returns:
    - List of configurations with organization, url, environment, gatewayType
    - Excludes sensitive fields (password, access token)
    """
    try:
        # Validate gatewayType from payload
        gateway_type = payload.get("gatewayType", "").lower()
        if gateway_type not in ["apigee-edge", "apigee-x"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gatewayType: {gateway_type}. Must be 'apigee-edge' or 'apigee-x'"
            )
        
        configs = []
        
        # Query Firestore for user configurations
        if firestore_db_x is not None:
            try:
                configs_ref = firestore_db_x.collection('apigee_configs')
                
                # Query by user email and gateway type
                query = configs_ref.where('probestackUserEmail', '==', user_id) \
                                  .where('gatewayType', '==', gateway_type)
                
                docs = list(query.stream())
                
                for doc in docs:
                    config_data = doc.to_dict()
                    
                    # Build safe config response (exclude sensitive fields)
                    safe_config = {
                        "organization": config_data.get("organization"),
                        "url": config_data.get("url"),
                        "environment": config_data.get("environment"),
                        "gatewayType": config_data.get("gatewayType")
                    }
                    
                    # Optionally include additional non-sensitive fields
                    if config_data.get("config_id"):
                        safe_config["config_id"] = config_data.get("config_id")
                    if config_data.get("config_name"):
                        safe_config["config_name"] = config_data.get("config_name")
                    if config_data.get("created_at"):
                        safe_config["created_at"] = config_data.get("created_at")
                    if config_data.get("verified"):
                        safe_config["verified"] = config_data.get("verified")
                    
                    configs.append(safe_config)
                
                logger.info(f"Found {len(configs)} configurations for user {user_id} with gatewayType {gateway_type}")
                
            except Exception as e:
                logger.error(f"Failed to query Firestore: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve configurations: {str(e)}"
                )
        else:
            # Fallback: check in-memory storage
            logger.warning("Firestore not available - checking in-memory storage")
            global _in_memory_config
            if _in_memory_config and isinstance(_in_memory_config, dict):
                if (_in_memory_config.get("probestackUserEmail") == user_id and
                    _in_memory_config.get("gatewayType") == gateway_type):
                    safe_config = {
                        "organization": _in_memory_config.get("organization"),
                        "url": _in_memory_config.get("url"),
                        "environment": _in_memory_config.get("environment"),
                        "gatewayType": _in_memory_config.get("gatewayType")
                    }
                    if _in_memory_config.get("config_id"):
                        safe_config["config_id"] = _in_memory_config.get("config_id")
                    if _in_memory_config.get("config_name"):
                        safe_config["config_name"] = _in_memory_config.get("config_name")
                    configs.append(safe_config)
        
        return {
            "success": True,
            "user_email": user_id,
            "gatewayType": gateway_type,
            "total_configs": len(configs),
            "configs": configs
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user configs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """Migrate a single resource using real Apigee X APIs"""

    try:
        # ======================================================
        # 1. LOAD CONFIG FROM DB (IF DB IS ENABLED)
        # ======================================================
        config = None
        if db is not None:
            try:
                config = await db.apigee_x_config.find_one({}, {"_id": 0})
            except Exception:
                config = None  # DB not available

        # ======================================================
        # 2. FALLBACK: LOAD CONFIG FROM UI PAYLOAD
        # ======================================================
        if not config:
            config = payload.get("apigee_x_config")

        # ======================================================
        # 3. STILL MISSING? THROW ERROR
        # ======================================================
        if not config:
            raise HTTPException(
                status_code=400, 
                detail="Apigee X configuration not found. Provide it in UI or save via /config/apigee-x."
            )

        # ======================================================
        # 4. ENSURE REQUIRED CONFIG FIELDS ARE PRESENT
        # ======================================================
        required = ["apigeex_org_name", "apigeex_env", "apigeex_token"]
        for r in required:
            if r not in config:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Missing required config field: {r}"
                )

        # Add default mgmt URL if missing
        if "apigeex_mgmt_url" not in config:
            config["apigeex_mgmt_url"] = "https://apigee.googleapis.com/v1/organizations/"

        # ======================================================
        # 5. PROCESS RESOURCE MIGRATION
        # ======================================================
        resource_type = payload.get("resource_type")
        resource_name = payload.get("resource_name")

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

        raw_type = resource_type
        resource_type = normalize_map.get(raw_type)

        if not resource_type:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported resource type: {raw_type}"
            )

        if not resource_type or not resource_name:
            raise HTTPException(status_code=400, detail="resource_type and resource_name are required")

        migrator = ApigeeXMigrator(config)

        if resource_type == "targetserver":
            result = migrator.migrate_target_server(resource_name)

        elif resource_type == "kvm":
            scope = payload.get("scope", "env")
            result = migrator.migrate_kvm(resource_name, scope)

        elif resource_type == "developer":
            result = migrator.migrate_developer(resource_name)

        elif resource_type == "apiproduct":
            result = migrator.migrate_product(resource_name)

        elif resource_type == "app":
            result = migrator.migrate_app(resource_name)

        elif resource_type == "proxy":
            result = migrator.migrate_proxy(resource_name.replace(".zip", ""))

        elif resource_type == "sharedflow":
            result = migrator.migrate_sharedflow(resource_name.replace(".zip", ""))

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported resource type: {resource_type}")

        return result

    except HTTPException:
        raise

    except Exception as e:
        logging.error(f"Migration failed: {str(e)}")
        return {
            "success": False,
            "resource_type": payload.get("resource_type"),
            "resource_name": payload.get("resource_name"),
            "message": str(e)
        }

@api_router.post("/migrate/multi-resource")
async def migrate_multiple_resources(payload: Dict[str, Any]):
    """Migrate multiple selected resources using real Apigee X APIs"""
    
    try:
        # Load config from DB or payload
        config = None
        if db is not None:
            try:
                config = await db.apigee_x_config.find_one({}, {"_id": 0})
            except Exception:
                config = None
        
        if not config:
            config = payload.get("apigee_x_config")
        
        if not config:
            raise HTTPException(
                status_code=400,
                detail="Apigee X configuration not found. Provide it in UI or save via /config/apigee-x."
            )
        
        # Validate required config fields
        required = ["apigeex_org_name", "apigeex_env", "apigeex_token"]
        for r in required:
            if r not in config:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required config field: {r}"
                )
        
        if "apigeex_mgmt_url" not in config:
            config["apigeex_mgmt_url"] = "https://apigee.googleapis.com/v1/organizations/"
        
        # Get resources list from payload
        resources = payload.get("resources", [])
        if not resources:
            raise HTTPException(status_code=400, detail="No resources provided for migration")
        
        # Check if deployment is requested
        deploy_after_migration = payload.get("deploy_after_migration", False)
        
        migrator = ApigeeXMigrator(config)
        results = []
        successful_count = 0
        failed_count = 0
        
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
        
        # Process each resource
        for resource in resources:
            resource_type = resource.get("type") or resource.get("resource_type")
            resource_name = resource.get("name") or resource.get("resource_name")
            
            if not resource_type or not resource_name:
                result = {
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "success": False,
                    "message": "Missing resource_type or resource_name",
                    "status_code": 400
                }
                results.append(result)
                failed_count += 1
                continue
            
            normalized_type = normalize_map.get(resource_type)
            if not normalized_type:
                result = {
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "success": False,
                    "message": f"Unsupported resource type: {resource_type}",
                    "status_code": 400
                }
                results.append(result)
                failed_count += 1
                continue
            
            # Migrate the resource
            try:
                if normalized_type == "targetserver":
                    result = migrator.migrate_target_server(resource_name)
                elif normalized_type == "kvm":
                    scope = resource.get("scope", "env")
                    result = migrator.migrate_kvm(resource_name, scope)
                elif normalized_type == "developer":
                    result = migrator.migrate_developer(resource_name)
                elif normalized_type == "apiproduct":
                    result = migrator.migrate_product(resource_name)
                elif normalized_type == "app":
                    result = migrator.migrate_app(resource_name)
                elif normalized_type == "proxy":
                    # Use deployment flag for proxies
                    result = migrator.migrate_proxy(resource_name.replace(".zip", ""), deploy_after_migration)
                elif normalized_type == "sharedflow":
                    # Use deployment flag for shared flows
                    result = migrator.migrate_sharedflow(resource_name.replace(".zip", ""), deploy_after_migration)
                else:
                    result = {
                        "resource_type": resource_type,
                        "resource_name": resource_name,
                        "success": False,
                        "message": f"Migration method not implemented for: {normalized_type}",
                        "status_code": 501
                    }
                
                results.append(result)
                
                if result.get("success", False):
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                result = {
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "success": False,
                    "message": f"Migration error: {str(e)}",
                    "status_code": 500
                }
                results.append(result)
                failed_count += 1
        
        # Create summary
        summary = {
            "total_requested": len(resources),
            "successful": successful_count,
            "failed": failed_count,
            "success_rate": (successful_count / len(resources) * 100) if resources else 0,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "deployment_enabled": deploy_after_migration
        }
        
        return {
            "success": True,
            "total_resources": len(resources),
            "successful_migrations": successful_count,
            "failed_migrations": failed_count,
            "results": results,
            "summary": summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Multi-resource migration failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Multi-resource migration failed: {str(e)}")

# === Deployment Routes ===

@api_router.post("/deploy/proxy")
async def deploy_proxy(payload: Dict[str, Any]):
    """Deploy a proxy to the specified environment"""
    try:
        # Load config
        config = None
        if db is not None:
            try:
                config = await db.apigee_x_config.find_one({}, {"_id": 0})
            except Exception:
                config = None
        
        if not config:
            config = payload.get("apigee_x_config")
        
        if not config:
            raise HTTPException(
                status_code=400,
                detail="Apigee X configuration not found. Provide it in UI or save via /config/apigee-x."
            )
        
        proxy_name = payload.get("proxy_name")
        revision = payload.get("revision", "1")
        
        if not proxy_name:
            raise HTTPException(status_code=400, detail="proxy_name is required")
        
        migrator = ApigeeXMigrator(config)
        result = migrator.deploy_proxy(proxy_name, revision)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Proxy deployment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Proxy deployment failed: {str(e)}")

@api_router.post("/deploy/sharedflow")
async def deploy_sharedflow(payload: Dict[str, Any]):
    """Deploy a shared flow to the specified environment"""
    try:
        # Load config
        config = None
        if db is not None:
            try:
                config = await db.apigee_x_config.find_one({}, {"_id": 0})
            except Exception:
                config = None
        
        if not config:
            config = payload.get("apigee_x_config")
        
        if not config:
            raise HTTPException(
                status_code=400,
                detail="Apigee X configuration not found. Provide it in UI or save via /config/apigee-x."
            )
        
        sf_name = payload.get("sharedflow_name")
        revision = payload.get("revision", "1")
        
        if not sf_name:
            raise HTTPException(status_code=400, detail="sharedflow_name is required")
        
        migrator = ApigeeXMigrator(config)
        result = migrator.deploy_sharedflow(sf_name, revision)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Shared flow deployment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Shared flow deployment failed: {str(e)}")

@api_router.post("/migrate-and-deploy/proxy")
async def migrate_and_deploy_proxy(payload: Dict[str, Any]):
    """Migrate and deploy a proxy in one operation"""
    try:
        # Load config
        config = None
        if db is not None:
            try:
                config = await db.apigee_x_config.find_one({}, {"_id": 0})
            except Exception:
                config = None
        
        if not config:
            config = payload.get("apigee_x_config")
        
        if not config:
            raise HTTPException(
                status_code=400,
                detail="Apigee X configuration not found. Provide it in UI or save via /config/apigee-x."
            )
        
        proxy_name = payload.get("proxy_name")
        
        if not proxy_name:
            raise HTTPException(status_code=400, detail="proxy_name is required")
        
        migrator = ApigeeXMigrator(config)
        result = migrator.migrate_and_deploy_proxy(proxy_name.replace(".zip", ""))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Proxy migration and deployment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Proxy migration and deployment failed: {str(e)}")

@api_router.post("/migrate-and-deploy/sharedflow")
async def migrate_and_deploy_sharedflow(payload: Dict[str, Any]):
    """Migrate and deploy a shared flow in one operation"""
    try:
        # Load config
        config = None
        if db is not None:
            try:
                config = await db.apigee_x_config.find_one({}, {"_id": 0})
            except Exception:
                config = None
        
        if not config:
            config = payload.get("apigee_x_config")
        
        if not config:
            raise HTTPException(
                status_code=400,
                detail="Apigee X configuration not found. Provide it in UI or save via /config/apigee-x."
            )
        
        sf_name = payload.get("sharedflow_name")
        
        if not sf_name:
            raise HTTPException(status_code=400, detail="sharedflow_name is required")
        
        migrator = ApigeeXMigrator(config)
        result = migrator.migrate_and_deploy_sharedflow(sf_name.replace(".zip", ""))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Shared flow migration and deployment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Shared flow migration and deployment failed: {str(e)}")

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

<<<<<<< HEAD
# Include the router in the main app
app.include_router(api_router)

# Add CORS middleware to handle cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],  # Allow all origins for development
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

=======
>>>>>>> b935b852f471b94baef8f0ef4eac03d76f2ce3da
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