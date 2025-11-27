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

# Firestore imports
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("[WARNING] Firestore not available - install google-cloud-firestore")

# In-memory storage when MongoDB is not available
_in_memory_config = None
# Import migration models and engine
from models.migration_models import MigrationJob, MigrationJobCreate, ValidationReport, DiffResult
from migration.migration_engine import MigrationEngine
from migration.assessment_engine import MigrationAssessment
from migration.apigee_x_migrator import ApigeeXMigrator
from utils.diff_calculator import DiffCalculator
from utils.mock_data import MockDataGenerator
import json


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Firestore initialization
firestore_db = None
if FIRESTORE_AVAILABLE:
    try:
        # Initialize Firestore client
        # If running on GCP, credentials are automatically detected
        # For local development, set GOOGLE_APPLICATION_CREDENTIALS env var
        firestore_db = firestore.Client()
        print("[OK] Firestore connected")
    except Exception as e:
        print(f"[WARNING] Firestore not available: {e}")
        print("[WARNING] Edge configuration will not be persisted to Firestore")
        firestore_db = None

# MongoDB connection (optional)
mongo_url = os.environ.get("MONGO_URL", "").strip().lower()

# Check if MongoDB is disabled
if mongo_url in ["none", "no", "false", "0", ""]:
    print("[WARNING] MongoDB disabled - running in NO-DATABASE mode")
    client = None
    db = None

else:
    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
        db = client[os.environ.get('DB_NAME', 'apigee_migration')]
        client.server_info()  # Test the connection
        print("[OK] MongoDB connected")
    except Exception as e:
        print(f"[WARNING] MongoDB not available: {e}")
        print("[WARNING] Running in no-database mode (configuration will not persist)")
        client = None
        db = None

# Create the main app without a prefix
app = FastAPI(title="Apigee Edge to X Migration API")

# CORS Configuration - MUST be set up BEFORE including routers
cors_origins_env = os.environ.get('CORS_ORIGINS', '').strip()
if cors_origins_env:
    # If CORS_ORIGINS is set, use it
    allowed_origins = [origin.strip() for origin in cors_origins_env.split(',') if origin.strip()]
else:
    # Default to common development origins
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

# Store allowed_origins for use in exception handlers
ALLOWED_ORIGINS = allowed_origins

# Add CORS middleware BEFORE including routers (important for proper CORS handling)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
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
    if db is None:
        return []
    
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
    if db is not None:
        job = await db.migration_jobs.find_one({"id": job_id}, {"_id": 0})
        if job:
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
    
    # Check in-memory storage
    job_dict = next((j for j in migration_jobs_memory if j["id"] == job_id), None)
    if not job_dict:
        raise HTTPException(status_code=404, detail="Migration job not found")
    
    return {
        "status": job_dict.get("status"),
        "total_resources": job_dict.get("total_resources", 0),
        "completed_resources": job_dict.get("completed_resources", 0),
        "failed_resources": job_dict.get("failed_resources", 0),
        "progress_percentage": (
            (job_dict.get("completed_resources", 0) / job_dict.get("total_resources", 1) * 100)
            if job_dict.get("total_resources", 0) > 0 else 0
        ),
        "logs": job_dict.get("logs", [])[-10:] if isinstance(job_dict.get("logs"), list) else []
    }

@api_router.get("/migrations/{job_id}/logs")
async def get_migration_logs(job_id: str):
    """Get migration logs"""
    # Try database first
    if db is not None:
        job = await db.migration_jobs.find_one({"id": job_id}, {"_id": 0})
        if job:
            return {
                "logs": job.get("logs", []),
                "errors": job.get("errors", []),
                "warnings": job.get("warnings", [])
            }
    
    # Check in-memory storage
    job_dict = next((j for j in migration_jobs_memory if j["id"] == job_id), None)
    if not job_dict:
        raise HTTPException(status_code=404, detail="Migration job not found")
    
    return {
        "logs": job_dict.get("logs", []),
        "errors": job_dict.get("errors", []),
        "warnings": job_dict.get("warnings", [])
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
        config["folder_name"] = "backend/data_edge"
        
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
    if db is not None:
        config = await db.apigee_x_config.find_one({}, {"_id": 0})
    else:
        global _in_memory_config
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
        config["folder_name"] = "backend/data_edge"
        
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

# === Edge Configuration Routes ===

class EdgeConfigCreate(BaseModel):
    orgId: str
    username: str
    env: str
    url: str
    password: str

@api_router.post("/config/edge")
async def save_edge_config(config: EdgeConfigCreate):
    """Save Apigee Edge configuration to Firestore"""
    try:
        config_data = {
            "orgId": config.orgId,
            "username": config.username,
            "env": config.env,
            "url": config.url,
            "password": config.password,  # In production, encrypt this
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Store in Firestore
        if firestore_db:
            doc_ref = firestore_db.collection('edge_configs').document(config.orgId)
            doc_ref.set(config_data)
            logger.info(f"Edge config saved to Firestore for org: {config.orgId}")
        else:
            # Fallback: store in memory if Firestore not available
            global _in_memory_config
            _in_memory_config = config_data
            logger.warning("Firestore not available, storing in memory")
        
        # Also store in MongoDB if available
        if db is not None:
            await db.edge_configs.update_one(
                {"orgId": config.orgId},
                {"$set": config_data},
                upsert=True
            )
            logger.info(f"Edge config saved to MongoDB for org: {config.orgId}")
        
        return {
            "success": True,
            "message": "Edge configuration saved successfully",
            "orgId": config.orgId
        }
    except Exception as e:
        logger.error(f"Failed to save Edge config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/config/edge/{org_id}")
async def get_edge_config(org_id: str):
    """Get saved Edge configuration from Firestore"""
    try:
        config_data = None
        
        # Try Firestore first
        if firestore_db:
            doc_ref = firestore_db.collection('edge_configs').document(org_id)
            doc = doc_ref.get()
            if doc.exists:
                config_data = doc.to_dict()
                logger.info(f"Edge config retrieved from Firestore for org: {org_id}")
        
        # Fallback to MongoDB
        if not config_data and db is not None:
            config_data = await db.edge_configs.find_one({"orgId": org_id}, {"_id": 0})
            if config_data:
                logger.info(f"Edge config retrieved from MongoDB for org: {org_id}")
        
        # Fallback to in-memory
        if not config_data:
            global _in_memory_config
            if _in_memory_config and _in_memory_config.get("orgId") == org_id:
                config_data = _in_memory_config
                logger.info(f"Edge config retrieved from memory for org: {org_id}")
        
        if not config_data:
            raise HTTPException(status_code=404, detail="Edge configuration not found")
        
        # Remove password from response for security
        safe_config = {**config_data}
        safe_config.pop("password", None)
        safe_config["password_set"] = bool(config_data.get("password"))
        
        return safe_config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Edge config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# === Discovery Routes ===

@api_router.post("/discover/real")
async def discover_real_resources(edge_config: EdgeConfigCreate):
    """Discover all resources from the Edge data folder and save Edge config to Firestore"""
    from utils.edge_data_parser import EdgeDataParser
    
    try:
        # Save Edge configuration to Firestore
        config_data = {
            "orgId": edge_config.orgId,
            "username": edge_config.username,
            "env": edge_config.env,
            "url": edge_config.url,
            "password": edge_config.password,  # In production, encrypt this
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Store in Firestore
        if firestore_db:
            doc_ref = firestore_db.collection('edge_configs').document(edge_config.orgId)
            doc_ref.set(config_data)
            logger.info(f"Edge config saved to Firestore during discovery for org: {edge_config.orgId}")
        else:
            logger.warning("Firestore not available, storing in memory")
            global _in_memory_config
            _in_memory_config = config_data
        
        # Also store in MongoDB if available
        if db is not None:
            await db.edge_configs.update_one(
                {"orgId": edge_config.orgId},
                {"$set": config_data},
                upsert=True
            )
            logger.info(f"Edge config saved to MongoDB during discovery for org: {edge_config.orgId}")
        
        # Parse resources from local files
        parser = EdgeDataParser()
        resources = parser.parse_all()
        
        return {
            "success": True,
            "resources": resources,
            "summary": parser.get_summary(),
            "config_saved": True
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add exception handler to ensure CORS headers are always included
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    """Ensure CORS headers are included in error responses"""
    origin = request.headers.get("origin", "")
    cors_origin = origin if origin in ALLOWED_ORIGINS else (ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": cors_origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected errors and include CORS headers"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    origin = request.headers.get("origin", "")
    cors_origin = origin if origin in ALLOWED_ORIGINS else (ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*")
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
        headers={
            "Access-Control-Allow-Origin": cors_origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
        }
    )

# === Replace deprecated @app.on_event with lifespan ===
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup (if needed later)
    yield
    # Shutdown
    client.close()

app.router.lifespan_context = lifespan


# === Allow python server.py to directly run the API ===
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )
