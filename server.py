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
from utils.firestore_logger import (
    set_firestore_client,
    log_info,
    log_warning,
    log_error,
    log_success,
    generate_operation_id
)
import json


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

# Initialize Firestore logger with the client
if firestore_db_x is not None:
    try:
        set_firestore_client(firestore_db_x)
        print("✓ Firestore logger initialized")
    except Exception as e:
        print(f"⚠ Failed to initialize Firestore logger: {e}")

# Create the main app without a prefix
app = FastAPI(title="Apigee Edge to X Migration API")

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
    """
    Get real-time migration progress
    
    Supports both:
    - job_id: MongoDB job ID (legacy)
    - migration_id: Firestore operation_id (new system)
    """
    try:
        # Check if job is in active jobs (MongoDB-based)
        if job_id in active_jobs:
            engine = active_jobs[job_id]
            return engine.get_progress()

        # Try to get from Firestore first (migration_id/operation_id)
        if firestore_db_x is not None:
            try:
                logs_ref = firestore_db_x.collection('migration_logs')
                # Query for logs with this operation_id
                query = logs_ref.where('operation_id', '==', job_id)
                docs = list(query.stream())
                
                if docs:
                    # Calculate progress from Firestore logs
                    logs_data = [doc.to_dict() for doc in docs]
                    
                    # Extract common metadata
                    resource_type = logs_data[0].get("resource_type") if logs_data else None
                    resource_name = logs_data[0].get("resource_name") if logs_data else None
                    
                    # Analyze logs to determine status
                    status = "completed"
                    has_errors = False
                    has_warnings = False
                    
                    # Get last 10 log messages
                    messages = []
                    for log_data in logs_data:
                        msg = log_data.get("message", "")
                        level = log_data.get("level", "INFO")
                        timestamp = log_data.get("timestamp")
                        
                        messages.append({
                            "message": msg,
                            "level": level,
                            "timestamp": timestamp.isoformat() if timestamp else None
                        })
                        
                        if level == "ERROR":
                            has_errors = True
                        if level == "WARNING":
                            has_warnings = True
                    
                    # Sort messages by timestamp
                    messages.sort(key=lambda x: x.get("timestamp") or "")
                    
                    # Determine status based on logs
                    if has_errors:
                        status = "failed"
                    elif any("completed successfully" in msg.get("message", "").lower() for msg in messages):
                        status = "completed"
                    elif any("starting" in msg.get("message", "").lower() for msg in messages):
                        if not any("completed" in msg.get("message", "").lower() for msg in messages):
                            status = "in_progress"
                    
                    # Calculate progress (for single resource migration)
                    total_resources = 1  # Single resource migration
                    completed_resources = 1 if status == "completed" else 0
                    failed_resources = 1 if status == "failed" else 0
                    
                    return {
                        "migration_id": job_id,
                        "status": status,
                        "resource_type": resource_type,
                        "resource_name": resource_name,
                        "total_resources": total_resources,
                        "completed_resources": completed_resources,
                        "failed_resources": failed_resources,
                        "progress_percentage": (
                            (completed_resources / total_resources * 100)
                            if total_resources > 0 else 0
                        ),
                        "logs": [msg["message"] for msg in messages[-10:]]
                    }
            except Exception as firestore_error:
                logger.warning(f"Failed to fetch from Firestore: {str(firestore_error)}")
                # Fall through to MongoDB lookup

        # If not found in Firestore, try MongoDB (legacy job_id)
        if db is None:
            raise HTTPException(
                status_code=404,
                detail=f"Migration not found. Checked both Firestore and MongoDB for ID: {job_id}"
            )

        job = await db.migration_jobs.find_one({"id": job_id}, {"_id": 0})
        if not job:
            raise HTTPException(
                status_code=404, 
                detail=f"Migration job not found in MongoDB. ID: {job_id}"
            )

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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get migration progress for {job_id}: {str(e)}")
        logger.exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve migration progress: {str(e)}"
        )

@api_router.get("/migrations/{migration_id}/logs")
async def get_migration_logs_by_id(
    migration_id: str,
    limit: int = 1000,
    level: Optional[str] = None
):
    """
    Get all logs for a specific migration ID
    
    Path Parameters:
    - migration_id: The migration ID (operation_id) to fetch logs for
    
    Query Parameters:
    - limit: Maximum number of logs to return (default: 1000, max: 1000)
    - level: Filter by log level (INFO, WARNING, ERROR) - optional
    
    Returns:
    - All log entries for the specified migration, ordered by timestamp (oldest first)
    """
    try:
        if firestore_db_x is None:
            raise HTTPException(
                status_code=503,
                detail="Firestore is not available. Logs cannot be retrieved."
            )
        
        # Validate limit
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 1000
        
        logger.info(f"Fetching logs for migration_id: {migration_id}")
        
        # Get logs collection and filter by operation_id (which equals migration_id)
        logs_ref = firestore_db_x.collection('migration_logs')
        # Query without order_by to avoid composite index requirement
        # We'll sort in Python after fetching
        query = logs_ref.where('operation_id', '==', migration_id)
        
        # Apply level filter if provided
        if level:
            level_upper = level.upper()
            if level_upper not in ['INFO', 'WARNING', 'ERROR']:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid log level: {level}. Must be INFO, WARNING, or ERROR"
                )
            query = query.where('level', '==', level_upper)
        
        # Execute query without order_by to avoid index requirement
        # We'll sort in Python instead
        docs = list(query.stream())
        
        # Sort by timestamp in Python (oldest first) to show chronological progression
        # Filter out docs without timestamp and sort
        docs_with_timestamp = []
        docs_without_timestamp = []
        for doc in docs:
            doc_data = doc.to_dict()
            if doc_data.get("timestamp"):
                docs_with_timestamp.append(doc)
            else:
                docs_without_timestamp.append(doc)
        
        # Sort by timestamp
        docs_with_timestamp.sort(key=lambda doc: doc.to_dict().get("timestamp") or datetime.min.replace(tzinfo=timezone.utc))
        
        # Combine: timestamped docs first (sorted), then docs without timestamp
        docs = docs_with_timestamp + docs_without_timestamp
        
        # Apply limit after sorting
        docs = docs[:limit]
        
        # Extract common metadata and messages
        common_metadata = {
            "resource_type": None,
            "resource_name": None
        }
        messages = []
        level_counts = {"INFO": 0, "WARNING": 0, "ERROR": 0}
        
        for doc in docs:
            doc_data = doc.to_dict()
            
            # Extract common metadata from first log entry (all should have same values)
            if common_metadata["resource_type"] is None:
                common_metadata["resource_type"] = doc_data.get("resource_type")
                common_metadata["resource_name"] = doc_data.get("resource_name")
            
            # Extract message with minimal fields for easy reading
            message_entry = {
                "message": doc_data.get("message", ""),
                "level": doc_data.get("level", "INFO"),
                "timestamp": doc_data.get("timestamp").isoformat() if doc_data.get("timestamp") else None
            }
            messages.append(message_entry)
            
            # Count log levels
            log_level = doc_data.get("level", "INFO")
            if log_level in level_counts:
                level_counts[log_level] += 1
        
        logger.info(f"Retrieved {len(messages)} log entries for migration {migration_id}")
        
        # Build response with common metadata at top level
        response = {
            "success": True,
            "migration_id": migration_id,
            "resource_type": common_metadata["resource_type"],
            "resource_name": common_metadata["resource_name"],
            "count": len(messages),
            "limit": limit,
            "summary": {
                "total_logs": len(messages),
                "info_count": level_counts["INFO"],
                "warning_count": level_counts["WARNING"],
                "error_count": level_counts["ERROR"]
            },
            "messages": messages
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch logs for migration {migration_id}: {str(e)}")
        logger.exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve logs: {str(e)}"
        )

@api_router.get("/migrations/{job_id}/logs")
async def get_migration_logs(
    job_id: str,
    operation_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 1000,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = "both"  # "mongo", "firestore", or "both"
):
    """
    Get migration logs from MongoDB and/or Firestore
    
    Path Parameters:
    - job_id: Migration job ID (for MongoDB logs)
    
    Query Parameters:
    - operation_id: Filter Firestore logs by operation ID
    - resource_type: Filter Firestore logs by resource type (app, proxy, kvm, etc.)
    - resource_name: Filter Firestore logs by resource name
    - level: Filter Firestore logs by log level (INFO, WARNING, ERROR)
    - limit: Maximum number of Firestore logs to return (default: 1000, max: 1000)
    - start_date: Start date in ISO format for Firestore logs (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - end_date: End date in ISO format for Firestore logs (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - source: Source of logs - "mongo", "firestore", or "both" (default: "both")
    
    Returns:
    - MongoDB logs (if available and source includes "mongo")
    - Firestore logs (if available and source includes "firestore")
    """
    result = {
        "job_id": job_id,
        "mongo_logs": None,
        "firestore_logs": None,
        "mongo_available": False,
        "firestore_available": False
    }
    
    # Get MongoDB logs if requested
    if source in ["mongo", "both"]:
        try:
            if db is not None:
                job = await db.migration_jobs.find_one({"id": job_id}, {"_id": 0})
                if job:
                    result["mongo_logs"] = {
                        "logs": job.get("logs", []),
                        "errors": job.get("errors", []),
                        "warnings": job.get("warnings", [])
                    }
                    result["mongo_available"] = True
                else:
                    result["mongo_logs"] = {
                        "logs": [],
                        "errors": [],
                        "warnings": []
                    }
            else:
                result["mongo_logs"] = {
                    "logs": [],
                    "errors": [],
                    "warnings": []
                }
        except Exception as e:
            logger.error(f"Failed to fetch MongoDB logs: {str(e)}")
            result["mongo_logs"] = {
                "logs": [],
                "errors": [],
                "warnings": [],
                "error": str(e)
            }
    
    # Get Firestore logs if requested
    if source in ["firestore", "both"]:
        try:
            if firestore_db_x is None:
                result["firestore_logs"] = {
                    "logs": [],
                    "error": "Firestore is not available"
                }
            else:
                # Validate limit
                if limit > 1000:
                    limit = 1000
                if limit < 1:
                    limit = 1000
                
                logger.info(f"Fetching Firestore migration logs with filters: operation_id={operation_id}, "
                           f"resource_type={resource_type}, resource_name={resource_name}, level={level}, limit={limit}")
                
                # Get logs collection
                logs_ref = firestore_db_x.collection('migration_logs')
                query = logs_ref
                
                # Apply filters
                if operation_id:
                    query = query.where('operation_id', '==', operation_id)
                
                if resource_type:
                    query = query.where('resource_type', '==', resource_type)
                
                if resource_name:
                    query = query.where('resource_name', '==', resource_name)
                
                if level:
                    level_upper = level.upper()
                    if level_upper not in ['INFO', 'WARNING', 'ERROR']:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid log level: {level}. Must be INFO, WARNING, or ERROR"
                        )
                    query = query.where('level', '==', level_upper)
                
                # Date filtering
                if start_date:
                    try:
                        from datetime import datetime as dt
                        # Try parsing ISO format
                        if 'T' in start_date:
                            start_dt = dt.fromisoformat(start_date.replace('Z', '+00:00'))
                        else:
                            start_dt = dt.fromisoformat(f"{start_date}T00:00:00+00:00")
                        start_timestamp = start_dt.replace(tzinfo=timezone.utc)
                        query = query.where('timestamp', '>=', start_timestamp)
                    except ValueError as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid start_date format: {start_date}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                        )
                
                if end_date:
                    try:
                        from datetime import datetime as dt
                        # Try parsing ISO format
                        if 'T' in end_date:
                            end_dt = dt.fromisoformat(end_date.replace('Z', '+00:00'))
                        else:
                            end_dt = dt.fromisoformat(f"{end_date}T23:59:59+00:00")
                        end_timestamp = end_dt.replace(tzinfo=timezone.utc)
                        query = query.where('timestamp', '<=', end_timestamp)
                    except ValueError as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid end_date format: {end_date}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                        )
                
                # Order by timestamp (newest first) and limit
                query = query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
                
                # Execute query
                docs = list(query.stream())
                
                # Convert Firestore documents to dictionaries
                logs = []
                for doc in docs:
                    doc_data = doc.to_dict()
                    log_entry = {
                        "id": doc.id,
                        "message": doc_data.get("message", ""),
                        "level": doc_data.get("level", "INFO"),
                        "timestamp": doc_data.get("timestamp").isoformat() if doc_data.get("timestamp") else None,
                        "operation_id": doc_data.get("operation_id"),
                        "resource_type": doc_data.get("resource_type"),
                        "resource_name": doc_data.get("resource_name"),
                        "metadata": doc_data.get("metadata", {})
                    }
                    logs.append(log_entry)
                
                logger.info(f"Retrieved {len(logs)} log entries from Firestore")
                
                result["firestore_logs"] = {
                    "logs": logs,
                    "count": len(logs),
                    "limit": limit,
                    "filters": {
                        "operation_id": operation_id,
                        "resource_type": resource_type,
                        "resource_name": resource_name,
                        "level": level,
                        "start_date": start_date,
                        "end_date": end_date
                    }
                }
                result["firestore_available"] = True
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Firestore logs: {str(e)}")
            logger.exception(e)
            result["firestore_logs"] = {
                "logs": [],
                "error": str(e)
            }
    
    return result


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

    # Generate operation ID for grouping logs
    operation_id = generate_operation_id()
    resource_type = payload.get("resource_type")
    resource_name = payload.get("resource_name")
    
    log_info("=" * 80, operation_id, resource_type, resource_name)
    log_info("🚀 Starting resource migration API call", operation_id, resource_type, resource_name)
    log_info(f"Request payload: resource_type={resource_type}, resource_name={resource_name}", 
             operation_id, resource_type, resource_name, 
             metadata={"operation_id": operation_id, "payload": payload})
    log_info("=" * 80, operation_id, resource_type, resource_name)

    try:
        # ======================================================
        # 1. LOAD CONFIG FROM INPUT PAYLOAD (FIRST PRIORITY)
        # ======================================================
        config = payload.get("apigee_x_config")
        
        if config:
            log_info("✓ Apigee X configuration found in input payload", operation_id, resource_type, resource_name)
            log_info("✓ Config is fetched from input", operation_id, resource_type, resource_name)
            log_info(f"Using config from payload (org: {config.get('apigeex_org_name')}, env: {config.get('apigeex_env')})", 
                     operation_id, resource_type, resource_name)
            if config.get("apigeex_token"):
                log_info("✓ Token found in input payload", operation_id, resource_type, resource_name)
        else:
            log_info("No Apigee X configuration found in input payload, attempting to fetch from Firestore", 
                     operation_id, resource_type, resource_name)

        # ======================================================
        # 2. FALLBACK: LOAD CONFIG FROM FIRESTORE (IF INPUT IS EMPTY)
        # ======================================================
        if not config and firestore_db_x is not None:
            try:
                log_info("Attempting to fetch Apigee X configuration from Firestore collection 'apigee_x_config'", 
                         operation_id, resource_type, resource_name)
                configs_ref = firestore_db_x.collection('apigee_x_config')

                # Get all documents from apigee_x_config collection
                docs = list(configs_ref.stream())

                if docs:
                    # Get the first document from the collection
                    doc = docs[0]
                    config_data = doc.to_dict()

                    log_info(f"Found document in apigee_x_config collection (doc_id: {doc.id})", 
                            operation_id, resource_type, resource_name)
                    log_info(f"Document data keys: {list(config_data.keys()) if config_data else 'None'}", 
                            operation_id, resource_type, resource_name)

                    # Transform Firestore document format to expected config format
                    # Handle both possible field name formats
                    config = {
                        "apigeex_org_name": config_data.get("organization") or config_data.get("apigeex_org_name"),
                        "apigeex_env": config_data.get("environment") or config_data.get("apigeex_env"),
                        "apigeex_token": config_data.get("apigeeOauthToken") or config_data.get("apigeex_token") or config_data.get("apigee_oauth_token"),
                        "apigeex_mgmt_url": config_data.get("url") or config_data.get("apigeex_mgmt_url") or "https://apigee.googleapis.com/v1/organizations/"
                    }

                    log_info("✓ Config is fetched from db", operation_id, resource_type, resource_name)
                    log_info(f"✓ Successfully fetched Apigee X configuration from Firestore (org: {config.get('apigeex_org_name')}, env: {config.get('apigeex_env')})", 
                            operation_id, resource_type, resource_name)
                    log_info(f"✓ Token fetched from Firestore database collection 'apigee_x_config' (doc_id: {doc.id})", 
                            operation_id, resource_type, resource_name)
                else:
                    log_warning("No documents found in Firestore collection 'apigee_x_config'", 
                              operation_id, resource_type, resource_name)
                    config = None

            except Exception as e:
                log_error(f"Failed to fetch config from Firestore collection 'apigee_x_config': {str(e)}", 
                         operation_id, resource_type, resource_name, metadata={"error": str(e)})
                logger.exception(e)
                config = None  # Firestore not available or query failed

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
        log_info("Validating Apigee X configuration fields...", operation_id, resource_type, resource_name)
        required = ["apigeex_org_name", "apigeex_env", "apigeex_token"]
        for r in required:
            if r not in config:
                log_error(f"❌ Missing required config field: {r}", operation_id, resource_type, resource_name)
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required config field: {r}"
                )
        log_info("✓ All required configuration fields are present", operation_id, resource_type, resource_name)

        # Add default mgmt URL if missing
        if "apigeex_mgmt_url" not in config:
            config["apigeex_mgmt_url"] = "https://apigee.googleapis.com/v1/organizations/"
            log_info(f"Using default management URL: {config['apigeex_mgmt_url']}", operation_id, resource_type, resource_name)
        else:
            log_info(f"Using management URL: {config['apigeex_mgmt_url']}", operation_id, resource_type, resource_name)
        
        log_info(f"Configuration validated - Org: {config.get('apigeex_org_name')}, Env: {config.get('apigeex_env')}", 
                operation_id, resource_type, resource_name)

        # ======================================================
        # 5. PROCESS RESOURCE MIGRATION
        # ======================================================
        log_info("-" * 80, operation_id, resource_type, resource_name)
        log_info("📋 Processing resource migration request", operation_id, resource_type, resource_name)
        log_info("-" * 80, operation_id, resource_type, resource_name)
        
        log_info(f"Received resource_type: '{resource_type}', resource_name: '{resource_name}'", 
                operation_id, resource_type, resource_name)

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
            log_error(f"❌ Unsupported resource type: {raw_type}", operation_id, resource_type, resource_name)
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported resource type: {raw_type}"
            )

        if not resource_type or not resource_name:
            log_error("❌ Missing required fields: resource_type and resource_name are required", 
                    operation_id, resource_type, resource_name)
            raise HTTPException(status_code=400, detail="resource_type and resource_name are required")

        log_info(f"✓ Resource type normalized: '{raw_type}' -> '{resource_type}'", operation_id, resource_type, resource_name)
        log_info(f"✓ Resource name: '{resource_name}'", operation_id, resource_type, resource_name)

        # ======================================================
        # 6. INITIALIZE APIGEE X MIGRATOR
        # ======================================================
        log_info("-" * 80, operation_id, resource_type, resource_name)
        log_info("🔧 Initializing Apigee X Migrator...", operation_id, resource_type, resource_name)
        log_info(f"   Organization: {config.get('apigeex_org_name')}", operation_id, resource_type, resource_name)
        log_info(f"   Environment: {config.get('apigeex_env')}", operation_id, resource_type, resource_name)
        log_info(f"   Management URL: {config.get('apigeex_mgmt_url')}", operation_id, resource_type, resource_name)
        
        migrator = ApigeeXMigrator(config)
        log_info("✓ Apigee X Migrator initialized successfully", operation_id, resource_type, resource_name)

        # ======================================================
        # 7. ESTABLISH APIGEE CONNECTION
        # ======================================================
        log_info("-" * 80, operation_id, resource_type, resource_name)
        log_info("🔌 Establishing connection to Apigee X...", operation_id, resource_type, resource_name)
        log_info(f"   Connecting to: {config.get('apigeex_mgmt_url')}{config.get('apigeex_org_name')}", 
                operation_id, resource_type, resource_name)
        
        try:
            connection_success, connection_message = migrator.verify_credentials()
            if connection_success:
                log_success("✅ Apigee X connection established successfully", operation_id, resource_type, resource_name)
                log_info(f"   Connection status: {connection_message}", operation_id, resource_type, resource_name,
                        metadata={"connection_status": connection_message})
            else:
                log_error(f"❌ Apigee X connection failed: {connection_message}", operation_id, resource_type, resource_name,
                         metadata={"connection_message": connection_message})
                raise HTTPException(
                    status_code=401,
                    detail=f"Failed to establish connection to Apigee X: {connection_message}"
                )
        except HTTPException:
            raise
        except Exception as e:
            log_error(f"❌ Error establishing Apigee X connection: {str(e)}", operation_id, resource_type, resource_name,
                     metadata={"error": str(e)})
            logger.exception(e)
            raise HTTPException(
                status_code=500,
                detail=f"Connection error: {str(e)}"
            )
        
        log_success("✅ Apigee X connection verified and ready", operation_id, resource_type, resource_name)
        
        # ======================================================
        # 8. EXECUTE RESOURCE CREATION/MIGRATION
        # ======================================================
        log_info("-" * 80, operation_id, resource_type, resource_name)
        log_info("🚀 Executing resource creation/migration...", operation_id, resource_type, resource_name)
        log_info(f"   Resource Type: {resource_type}", operation_id, resource_type, resource_name)
        log_info(f"   Resource Name: {resource_name}", operation_id, resource_type, resource_name)
        log_info("-" * 80, operation_id, resource_type, resource_name)

        try:
            if resource_type == "targetserver":
                log_info(f"📦 Migrating target server: {resource_name}", operation_id, resource_type, resource_name)
                result = migrator.migrate_target_server(resource_name)

            elif resource_type == "kvm":
                scope = payload.get("scope", "env")
                log_info(f"📦 Migrating KVM: {resource_name} (scope: {scope})", operation_id, resource_type, resource_name,
                        metadata={"scope": scope})
                result = migrator.migrate_kvm(resource_name, scope)

            elif resource_type == "developer":
                log_info(f"📦 Migrating developer: {resource_name}", operation_id, resource_type, resource_name)
                result = migrator.migrate_developer(resource_name)

            elif resource_type == "apiproduct":
                log_info(f"📦 Migrating API product: {resource_name}", operation_id, resource_type, resource_name)
                result = migrator.migrate_product(resource_name)

            elif resource_type == "app":
                log_info(f"📦 Migrating app: {resource_name}", operation_id, resource_type, resource_name)
                result = migrator.migrate_app(resource_name)

            elif resource_type == "proxy":
                clean_name = resource_name.replace(".zip", "")
                log_info(f"📦 Migrating proxy: {clean_name} (from: {resource_name})", operation_id, resource_type, resource_name,
                        metadata={"original_name": resource_name, "clean_name": clean_name})
                result = migrator.migrate_proxy(clean_name)

            elif resource_type == "sharedflow":
                clean_name = resource_name.replace(".zip", "")
                log_info(f"📦 Migrating shared flow: {clean_name} (from: {resource_name})", operation_id, resource_type, resource_name,
                        metadata={"original_name": resource_name, "clean_name": clean_name})
                result = migrator.migrate_sharedflow(clean_name)

            else:
                log_error(f"❌ Unsupported resource type: {resource_type}", operation_id, resource_type, resource_name)
                raise HTTPException(status_code=400, detail=f"Unsupported resource type: {resource_type}")

            # Log result details
            log_info("-" * 80, operation_id, resource_type, resource_name)
            log_info("📊 Migration execution completed", operation_id, resource_type, resource_name)
            log_info(f"   Result: {result}", operation_id, resource_type, resource_name, metadata={"result": str(result)})
            
            if isinstance(result, dict):
                success = result.get("success", False)
                if success:
                    log_success("✅ Resource creation/migration completed successfully", operation_id, resource_type, resource_name)
                    log_info(f"   Resource: {resource_type}/{resource_name}", operation_id, resource_type, resource_name)
                else:
                    log_warning(f"⚠️  Resource creation/migration completed with warnings", operation_id, resource_type, resource_name)
                    log_warning(f"   Message: {result.get('message', 'No message provided')}", operation_id, resource_type, resource_name,
                              metadata={"message": result.get('message', 'No message provided')})
            else:
                log_success("✅ Resource creation/migration completed", operation_id, resource_type, resource_name)
            
            log_info("=" * 80, operation_id, resource_type, resource_name)
            log_success("🎉 API call completed successfully", operation_id, resource_type, resource_name)
            log_info("=" * 80, operation_id, resource_type, resource_name)

            # Ensure result is a dict and add migration_id
            if isinstance(result, dict):
                result["migration_id"] = operation_id
                # Also add operation_id for backward compatibility
                result["operation_id"] = operation_id
            else:
                # If result is not a dict, convert it
                result = {
                    "success": True,
                    "migration_id": operation_id,
                    "operation_id": operation_id,
                    "result": result
                }

            return result

        except Exception as migration_error:
            log_error("-" * 80, operation_id, resource_type, resource_name)
            log_error(f"❌ Error during resource creation/migration: {str(migration_error)}", operation_id, resource_type, resource_name,
                     metadata={"error": str(migration_error), "error_type": type(migration_error).__name__})
            log_error(f"   Resource Type: {resource_type}", operation_id, resource_type, resource_name)
            log_error(f"   Resource Name: {resource_name}", operation_id, resource_type, resource_name)
            logger.exception(migration_error)
            raise

    except HTTPException as http_ex:
        # Use payload values in case resource_type/resource_name weren't set yet
        error_resource_type = resource_type if 'resource_type' in locals() else payload.get('resource_type', 'unknown')
        error_resource_name = resource_name if 'resource_name' in locals() else payload.get('resource_name', 'unknown')
        
        log_error("=" * 80, operation_id, error_resource_type, error_resource_name)
        log_error(f"❌ HTTP Exception occurred: {http_ex.status_code} - {http_ex.detail}", operation_id, error_resource_type, error_resource_name,
                 metadata={"status_code": http_ex.status_code, "detail": http_ex.detail})
        log_error("=" * 80, operation_id, error_resource_type, error_resource_name)
        raise

    except Exception as e:
        # Use payload values in case resource_type/resource_name weren't set yet
        error_resource_type = resource_type if 'resource_type' in locals() else payload.get('resource_type', 'unknown')
        error_resource_name = resource_name if 'resource_name' in locals() else payload.get('resource_name', 'unknown')
        
        log_error("=" * 80, operation_id, error_resource_type, error_resource_name)
        log_error(f"❌ Migration API call failed with exception: {str(e)}", operation_id, error_resource_type, error_resource_name,
                 metadata={"error": str(e), "error_type": type(e).__name__})
        log_error(f"   Resource Type: {error_resource_type}", operation_id, error_resource_type, error_resource_name)
        log_error(f"   Resource Name: {error_resource_name}", operation_id, error_resource_type, error_resource_name)
        logger.exception(e)
        log_error("=" * 80, operation_id, error_resource_type, error_resource_name)
        
        # Ensure operation_id is available even in error cases
        error_operation_id = operation_id if 'operation_id' in locals() else generate_operation_id()
        
        return {
            "success": False,
            "migration_id": error_operation_id,
            "operation_id": error_operation_id,
            "resource_type": payload.get("resource_type"),
            "resource_name": payload.get("resource_name"),
            "message": str(e)
        }

@api_router.get("/migrate/logs")
async def get_all_migration_logs(
    operation_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 100,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get all migration logs from Firestore with optional filtering
    (Does not require a job_id - fetches all logs)
    
    Query Parameters:
    - operation_id: Filter logs by operation ID (groups all logs from one operation)
    - resource_type: Filter by resource type (app, proxy, kvm, etc.)
    - resource_name: Filter by resource name
    - level: Filter by log level (INFO, WARNING, ERROR)
    - limit: Maximum number of logs to return (default: 100, max: 1000)
    - start_date: Start date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - end_date: End date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    
    Returns:
    - List of log entries with metadata
    """
    try:
        # Validate limit
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 100
        
        # Check if Firestore is available
        if firestore_db_x is None:
            raise HTTPException(
                status_code=503,
                detail="Firestore is not available. Logs cannot be retrieved."
            )
        
        logger.info(f"Fetching all migration logs with filters: operation_id={operation_id}, "
                   f"resource_type={resource_type}, resource_name={resource_name}, level={level}, limit={limit}")
        
        # Get logs collection
        logs_ref = firestore_db_x.collection('migration_logs')
        query = logs_ref
        
        # Apply filters
        if operation_id:
            query = query.where('operation_id', '==', operation_id)
        
        if resource_type:
            query = query.where('resource_type', '==', resource_type)
        
        if resource_name:
            query = query.where('resource_name', '==', resource_name)
        
        if level:
            level_upper = level.upper()
            if level_upper not in ['INFO', 'WARNING', 'ERROR']:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid log level: {level}. Must be INFO, WARNING, or ERROR"
                )
            query = query.where('level', '==', level_upper)
        
        # Date filtering
        if start_date:
            try:
                from datetime import datetime as dt
                # Try parsing ISO format
                if 'T' in start_date:
                    start_dt = dt.fromisoformat(start_date.replace('Z', '+00:00'))
                else:
                    start_dt = dt.fromisoformat(f"{start_date}T00:00:00+00:00")
                start_timestamp = start_dt.replace(tzinfo=timezone.utc)
                query = query.where('timestamp', '>=', start_timestamp)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid start_date format: {start_date}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                )
        
        if end_date:
            try:
                from datetime import datetime as dt
                # Try parsing ISO format
                if 'T' in end_date:
                    end_dt = dt.fromisoformat(end_date.replace('Z', '+00:00'))
                else:
                    end_dt = dt.fromisoformat(f"{end_date}T23:59:59+00:00")
                end_timestamp = end_dt.replace(tzinfo=timezone.utc)
                query = query.where('timestamp', '<=', end_timestamp)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid end_date format: {end_date}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Order by timestamp (newest first) and limit
        query = query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
        
        # Execute query
        docs = list(query.stream())
        
        # Convert Firestore documents to dictionaries
        logs = []
        for doc in docs:
            doc_data = doc.to_dict()
            log_entry = {
                "id": doc.id,
                "message": doc_data.get("message", ""),
                "level": doc_data.get("level", "INFO"),
                "timestamp": doc_data.get("timestamp").isoformat() if doc_data.get("timestamp") else None,
                "operation_id": doc_data.get("operation_id"),
                "resource_type": doc_data.get("resource_type"),
                "resource_name": doc_data.get("resource_name"),
                "metadata": doc_data.get("metadata", {})
            }
            logs.append(log_entry)
        
        logger.info(f"Retrieved {len(logs)} log entries from Firestore")
        
        return {
            "success": True,
            "count": len(logs),
            "limit": limit,
            "filters": {
                "operation_id": operation_id,
                "resource_type": resource_type,
                "resource_name": resource_name,
                "level": level,
                "start_date": start_date,
                "end_date": end_date
            },
            "logs": logs
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch migration logs: {str(e)}")
        logger.exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve logs: {str(e)}"
        )

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

# Include the router in the main app (after CORS middleware)
app.include_router(api_router)

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
            "Access-Control-Allow-Origin": allow_origin,
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, Origin, Access-Control-Request-Method, Access-Control-Request-Headers",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "3600",
        }
    )

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