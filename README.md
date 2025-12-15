# MigrationX Backend Service

A comprehensive FastAPI-based service for assessing and migrating Apigee Edge resources to Apigee X. The service provides assessment capabilities, dependency analysis, and migration orchestration with support for both local file systems and Google Cloud Storage.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Usage Examples](#usage-examples)
- [Architecture](#architecture)
- [Firestore Collections](#firestore-collections)
- [Error Handling](#error-handling)
- [Development](#development)

## Features

### Assessment Capabilities
- **V1 Assessment** (`/api/assess`): Reads from local `data_edge` directory
- **V2 Assessment** (`/api/assess/v2`): Reads from Google Cloud Storage with automatic path construction
- Policy compatibility analysis
- Dependency mapping and migration order determination
- Resource readiness assessment (ready/needs_attention/blocked)

### Migration Features
- Resource migration orchestration
- Background job processing
- Progress tracking
- Validation and diff calculation

### Data Sources
- Local file system (V1)
- Google Cloud Storage (V2)
- Non-blocking GCS reads with failure logging

### Observability
- Structured logging to Firestore
- Operation ID tracking
- Comprehensive error logging
- Failure diagnostics

## Prerequisites

- Python 3.8+
- Google Cloud Platform account (for GCS and Firestore)
- MongoDB (optional, for job storage)
- Apigee Edge credentials (for migration operations)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd MigrationX_backend
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Configuration

### Environment Variables

#### Required for V2 Assessment
```bash
# Google Cloud Storage bucket name for assessment data
GCS_ASSESSMENT_BUCKET_NAME=your-gcs-bucket-name
```

#### Optional Configuration
```bash
# MongoDB connection (set to "none" to disable)
MONGO_URL=mongodb://localhost:27017
DB_NAME=apigee_migration

# Firestore (uses default credentials if not set)
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json
GCP_PROJECT_ID=your-project-id
FIRESTORE_EMULATOR_HOST=localhost:8080  # For local development

# Server configuration
PORT=8080
CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# Apigee verification
ENABLE_APIGEE_VERIFICATION=false
```

### Google Cloud Setup

1. **Create a GCS bucket** for storing Apigee Edge export data
2. **Set up Firestore** in your GCP project
3. **Configure service account** with appropriate permissions:
   - Storage Object Viewer (for GCS reads)
   - Cloud Datastore User (for Firestore writes)
4. **Set credentials** via environment variable or default application credentials

### GCS Bucket Structure

The V2 assessment endpoint expects the following structure in your GCS bucket:

```
{organization}/
  {environment}/
    apiproducts/
      *.json
    apps/
      *.json
    developers/
      *.json
    keyvaluemaps/
      env/
        {environment}/
          *.json
      org/
        *.json
    proxies/
      *.zip
    sharedflows/
      *.zip
    targetservers/
      env/
        {environment}/
          *.json
```

## API Endpoints

### Assessment Endpoints

#### POST `/api/assess` (V1)
Performs migration assessment using local `data_edge` directory.

**Request:**
```json
No request body required
```

**Response:**
```json
{
  "success": true,
  "assessment": {
    "summary": {
      "total_proxies": 5,
      "total_shared_flows": 3,
      "ready_to_migrate": 20,
      "needs_attention": 5,
      "blocked": 2,
      "total_issues": 5,
      "total_warnings": 10
    },
    "proxy_assessments": [...],
    "shared_flow_assessments": [...],
    "dependencies": {...},
    "migration_order": [...],
    "overall_status": "ready"
  }
}
```

#### POST `/api/assess/v2` (V2)
Performs migration assessment using data from Google Cloud Storage.

**Request:**
```json
{
  "organization": "arctic-inkwell-480005-q6",
  "environment": "eval",
  "transactionId": "XUYI_arctic-inkwell-480005-q6_eval_20251212012420"
}
```

**Response:**
```json
{
  "success": true,
  "assessment": {
    "summary": {...},
    "proxy_assessments": [...],
    "shared_flow_assessments": [...],
    "target_server_assessments": [...],
    "kvm_assessments": [...],
    "api_product_assessments": [...],
    "app_assessments": [...],
    "developer_assessments": [...],
    "dependencies": {...},
    "migration_order": [...],
    "overall_status": "ready|needs_attention|blocked",
    "total_issues": 0,
    "total_warnings": 0
  }
}
```

**Features:**
- Automatically constructs GCS path: `{organization}/{environment}/`
- Non-blocking GCS reads (continues on individual failures)
- Logs failures to Firestore `gcs_read_failures` collection
- Persists results to Firestore `assessment_apigee_results` collection

### Other Endpoints

- `GET /api/status` - Service health check
- `GET /api/dependencies` - Get dependency graph
- `POST /api/migrations` - Create migration job
- `GET /api/migrations/{job_id}` - Get migration job status
- `POST /api/migrations/{job_id}/start` - Start migration job
- `GET /api/migrations/{job_id}/progress` - Get migration progress

## Usage Examples

### V2 Assessment with curl

```bash
curl -X POST "http://localhost:8080/api/assess/v2" \
  -H "Content-Type: application/json" \
  -d '{
    "organization": "arctic-inkwell-480005-q6",
    "environment": "eval",
    "transactionId": "XUYI_arctic-inkwell-480005-q6_eval_20251212012420"
  }'
```

### V2 Assessment with Python

```python
import requests

url = "http://localhost:8080/api/assess/v2"
payload = {
    "organization": "arctic-inkwell-480005-q6",
    "environment": "eval",
    "transactionId": "XUYI_arctic-inkwell-480005-q6_eval_20251212012420"
}

response = requests.post(url, json=payload)
result = response.json()

print(f"Overall Status: {result['assessment']['overall_status']}")
print(f"Total Issues: {result['assessment']['total_issues']}")
print(f"Total Warnings: {result['assessment']['total_warnings']}")
```

### Running the Server

```bash
# Development mode
python server.py

# Production mode with uvicorn
uvicorn server:app --host 0.0.0.0 --port 8080
```

## Architecture

### V2 Assessment Flow

```
1. Request Validation
   ├─ Validate organization, environment, transactionId
   └─ Read GCS_ASSESSMENT_BUCKET_NAME from environment

2. Service Initialization
   ├─ Generate operation_id
   ├─ Construct GCS prefix: {organization}/{environment}/
   └─ Initialize GCS Storage Client

3. Data Fetching (Non-Blocking)
   ├─ Fetch proxies from {org}/{env}/proxies/
   ├─ Fetch shared flows from {org}/{env}/sharedflows/
   ├─ Fetch developers from {org}/{env}/developers/
   ├─ Fetch apps from {org}/{env}/apps/
   ├─ Fetch API products from {org}/{env}/apiproducts/
   ├─ Fetch target servers from {org}/{env}/targetservers/env/{env}/
   └─ Fetch KVMs from {org}/{env}/keyvaluemaps/env/{env}/
   
   Each fetch:
   - Continues on failure
   - Logs failures to Firestore
   - Tracks failure count

4. Assessment Execution
   ├─ Run MigrationAssessment on all resources
   ├─ Analyze dependencies
   └─ Generate migration order

5. Firestore Persistence
   └─ Write results to assessment_apigee_results collection

6. Response
   └─ Return assessment results (V1-compatible format)
```

### Key Components

- **GCSAssessmentService**: Handles GCS-based data fetching and assessment
- **MigrationAssessment**: Analyzes resource migration readiness
- **DependencyAnalyzer**: Maps resource dependencies and determines migration order
- **Firestore Logger**: Structured logging with operation tracking

## Firestore Collections

### `assessment_apigee_results`
Stores complete assessment results for each assessment run.

**Document Structure:**
```json
{
  "operation_id": "unique-id",
  "timestamp": "2024-01-15T10:30:00Z",
  "bucket": "gcs-bucket-name",
  "gcs_prefix": "org/env/",
  "organization": "org-name",
  "environment": "env-name",
  "transactionId": "transaction-id",
  "assessment": {
    // Full assessment object
  },
  "gcs_failures_count": 0
}
```

**Query Examples:**
```python
# Get assessment by operation_id
assessment = firestore.collection('assessment_apigee_results').document(operation_id).get()

# Get assessments by organization
assessments = firestore.collection('assessment_apigee_results')\
    .where('organization', '==', 'org-name')\
    .order_by('timestamp', direction=firestore.Query.DESCENDING)\
    .limit(10)\
    .stream()
```

### `gcs_read_failures`
Stores individual GCS read failures for troubleshooting.

**Document Structure:**
```json
{
  "operation_id": "unique-id",
  "timestamp": "2024-01-15T10:30:15Z",
  "bucket_name": "gcs-bucket-name",
  "gcs_prefix": "org/env/",
  "organization": "org-name",
  "environment": "env-name",
  "transactionId": "transaction-id",
  "resource_type": "proxy",
  "operation": "download_and_parse",
  "gcs_path": "org/env/proxies/my-proxy.zip",
  "resource_name": "my-proxy",
  "error": "404 Not Found",
  "error_type": "NotFound",
  "blob_size": 1024000,
  "blob_updated": "2024-01-10T08:00:00Z",
  "additional_context": {}
}
```

**Query Examples:**
```python
# Get failures for a specific assessment
failures = firestore.collection('gcs_read_failures')\
    .where('operation_id', '==', operation_id)\
    .stream()

# Get failures by resource type
failures = firestore.collection('gcs_read_failures')\
    .where('resource_type', '==', 'proxy')\
    .where('organization', '==', 'org-name')\
    .stream()
```

### `migration_logs`
Stores structured logs for all operations.

**Document Structure:**
```json
{
  "message": "Starting V2 assessment workflow",
  "level": "INFO",
  "timestamp": "2024-01-15T10:30:00Z",
  "operation_id": "unique-id",
  "resource_type": "ASSESSMENT",
  "resource_name": "V2",
  "metadata": {
    "bucket": "gcs-bucket-name",
    "organization": "org-name"
  }
}
```

## Error Handling

### V2 Assessment Error Scenarios

1. **Missing Environment Variable**
   - Error: `GCS_ASSESSMENT_BUCKET_NAME` not set
   - Response: HTTP 400 with descriptive message

2. **GCS Client Initialization Failure**
   - Error: Cannot connect to GCS
   - Response: HTTP 500 with error details

3. **Individual Resource Read Failures**
   - Behavior: Logged to Firestore, process continues
   - Response: Assessment continues with available data
   - Tracking: `gcs_failures_count` in response metadata

4. **Assessment Execution Failure**
   - Error: Assessment engine failure
   - Response: HTTP 500 with error details

5. **Firestore Write Failure**
   - Behavior: Logged but doesn't fail request
   - Response: Assessment still returns successfully

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

## Development

### Project Structure

```
MigrationX_backend/
├── server.py                 # Main FastAPI application
├── migration/                # Migration engine modules
│   ├── assessment_engine.py  # Assessment logic
│   ├── dependency_analyzer.py
│   └── ...
├── utils/                    # Utility modules
│   ├── gcs_assessment_service.py  # V2 GCS assessment service
│   ├── edge_data_parser.py  # V1 local file parser
│   └── firestore_logger.py  # Structured logging
├── models/                   # Pydantic models
├── clients/                  # API clients
└── data_edge/               # Local data directory (V1)
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest
```

### Code Style

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

### Adding New Features

1. **New Assessment Endpoint**: Extend `GCSAssessmentService` or create new service
2. **New Resource Type**: Add fetch method following existing patterns
3. **New Firestore Collection**: Update documentation and add query examples

## Troubleshooting

### Common Issues

1. **GCS Authentication Errors**
   - Verify `GOOGLE_APPLICATION_CREDENTIALS` is set correctly
   - Check service account has required permissions

2. **Firestore Connection Issues**
   - Verify project ID is correct
   - Check Firestore API is enabled in GCP project

3. **GCS Read Failures**
   - Check bucket structure matches expected format
   - Verify organization/environment paths are correct
   - Review `gcs_read_failures` collection in Firestore

4. **Assessment Returns Empty Results**
   - Verify data exists in GCS at expected paths
   - Check GCS read failures in Firestore
   - Review operation logs using `operation_id`

## License

[Add your license information here]

## Support

For issues and questions:
- Create an issue in the repository
- Check Firestore logs using `operation_id` from responses
- Review `gcs_read_failures` collection for diagnostic information

