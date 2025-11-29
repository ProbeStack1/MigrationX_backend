# Complete API Documentation

## Base URL
```
http://localhost:8080/api
```

## Table of Contents
1. [Health Check & Status](#health-check--status)
2. [Migration Jobs](#migration-jobs) 
3. [Edge Data & Discovery](#edge-data--discovery)
4. [Configuration](#configuration)
5. [Assessment & Dependencies](#assessment--dependencies)
6. [Migration Operations](#migration-operations)
7. [Mock Data](#mock-data)
8. [Diff & Comparison](#diff--comparison)

---

## Health Check & Status

### 1. Root Endpoint
**GET** `/api/`

**Description:** Returns API information and status.

**Request:** None

**Response:**
```json
{
  "message": "Apigee Edge to X Migration API",
  "version": "1.0.0",
  "status": "running"
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/'
```

---

### 2. Get Status Checks
**GET** `/api/status`

**Description:** Get system status checks.

**Request:** None

**Response:** `List[StatusCheck]`
```json
[
  {
    "service": "database",
    "status": "healthy",
    "timestamp": "2024-01-01T00:00:00Z"
  }
]
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/status'
```

---

## Migration Jobs

### 3. Create Migration Job
**POST** `/api/migrations`

**Description:** Create a new migration job with assessment.

**Request Body:** `MigrationJobCreate`
```json
{
  "name": "Migration Job 1",
  "edge_org": "my-edge-org",
  "edge_env": "prod",
  "apigee_x_org": "my-x-org",
  "apigee_x_env": "prod",
  "dry_run": false,
  "resource_types": ["proxies", "shared_flows"]
}
```

**Response:** `MigrationJob`
```json
{
  "id": "uuid-here",
  "name": "Migration Job 1",
  "status": "pending",
  "edge_org": "my-edge-org",
  "edge_env": "prod",
  "apigee_x_org": "my-x-org",
  "apigee_x_env": "prod",
  "dry_run": false,
  "resources": [...],
  "total_resources": 10,
  "completed_resources": 0,
  "failed_resources": 0,
  "created_at": "2024-01-01T00:00:00Z",
  "started_at": null,
  "completed_at": null,
  "logs": [],
  "errors": [],
  "warnings": []
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/migrations' \
  --header 'Content-Type: application/json' \
  --data '{
    "name": "Migration Job 1",
    "edge_org": "my-edge-org",
    "edge_env": "prod",
    "apigee_x_org": "my-x-org",
    "apigee_x_env": "prod",
    "dry_run": false
  }'
```

---

### 4. List Migration Jobs
**GET** `/api/migrations`

**Description:** Get all migration jobs.

**Request:** None

**Response:** `List[MigrationJob]`
```json
[
  {
    "id": "uuid-1",
    "name": "Migration Job 1",
    "status": "completed",
    ...
  }
]
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/migrations'
```

---

### 5. Get Migration Job
**GET** `/api/migrations/{job_id}`

**Description:** Get a specific migration job by ID.

**Path Parameters:**
- `job_id` (string, required): Migration job ID

**Response:** `MigrationJob`
```json
{
  "id": "uuid-here",
  "name": "Migration Job 1",
  "status": "running",
  ...
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/migrations/{job_id}'
```

---

### 6. Start Migration Job
**POST** `/api/migrations/{job_id}/start`

**Description:** Start a migration job execution.

**Path Parameters:**
- `job_id` (string, required): Migration job ID

**Request:** None

**Response:**
```json
{
  "message": "Migration started",
  "job_id": "uuid-here"
}
```

**cURL:**
```bash
curl --location --request POST 'http://localhost:8080/api/migrations/{job_id}/start'
```

---

### 7. Get Migration Progress
**GET** `/api/migrations/{job_id}/progress`

**Description:** Get real-time migration progress.

**Path Parameters:**
- `job_id` (string, required): Migration job ID

**Response:**
```json
{
  "status": "running",
  "total_resources": 100,
  "completed_resources": 45,
  "failed_resources": 2,
  "progress_percentage": 45.0,
  "logs": ["Log entry 1", "Log entry 2"]
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/migrations/{job_id}/progress'
```

---

### 8. Get Migration Logs
**GET** `/api/migrations/{job_id}/logs`

**Description:** Get migration logs for a job.

**Path Parameters:**
- `job_id` (string, required): Migration job ID

**Response:**
```json
{
  "logs": ["Log 1", "Log 2"],
  "errors": ["Error 1"],
  "warnings": ["Warning 1"]
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/migrations/{job_id}/logs'
```

---

## Edge Data & Discovery

### 9. Get Mock Edge Export
**GET** `/api/mock/edge-export`

**Description:** Get mock Edge export data for demo purposes.

**Request:** None

**Response:**
```json
{
  "proxies": [...],
  "shared_flows": [...],
  "target_servers": [...],
  "kvms": [...],
  "api_products": [...],
  "developers": [...],
  "developer_apps": [...]
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/mock/edge-export'
```

---

### 10. Get Real Edge Export
**GET** `/api/edge/real-export`

**Description:** Get real Edge export data from uploaded files.

**Request:** None

**Response:**
```json
{
  "proxies": [...],
  "shared_flows": [...],
  ...
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/edge/real-export'
```

---

### 11. Get Edge Summary
**GET** `/api/edge/summary`

**Description:** Get summary of Edge resources.

**Request:** None

**Response:**
```json
{
  "total_proxies": 10,
  "total_shared_flows": 5,
  "total_target_servers": 8,
  ...
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/edge/summary'
```

---

### 12. Get Edge Assessment
**GET** `/api/edge/assessment`

**Description:** Get migration assessment for Edge resources with dependency analysis.

**Request:** None

**Response:**
```json
{
  "proxy_assessments": [...],
  "shared_flow_assessments": [...],
  "dependencies": {...},
  "migration_order": [...]
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/edge/assessment'
```

---

### 13. Discover Real Resources
**GET** `/api/discover/real`

**Description:** Discover all resources from the Edge data folder.

**Request:** None

**Response:**
```json
{
  "success": true,
  "resources": {
    "proxies": [...],
    "shared_flows": [...],
    ...
  },
  "summary": {
    "total_proxies": 10,
    ...
  }
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/discover/real'
```

---

## Configuration

### 14. Get Environment Variables
**GET** `/api/config/environment`

**Description:** Get list of all environment variables needed for the application and their current values.

**Request:** None

**Response:**
```json
{
  "environment_variables": {
    "ENABLE_APIGEE_VERIFICATION": {
      "description": "Enable real Apigee connection verification...",
      "required": false,
      "sensitive": false,
      "default": "false",
      "current_value": "false",
      "is_set": false,
      "effective_value": "False"
    },
    "MONGO_URL": {
      "description": "MongoDB connection string...",
      "required": false,
      "sensitive": true,
      "current_value": "***MASKED***",
      "is_set": true,
      "effective_value": "enabled"
    },
    ...
  },
  "connection_status": {
    "mongodb": {
      "enabled": false,
      "status": "disabled or unavailable"
    },
    "firestore": {
      "enabled": true,
      "status": "connected",
      "available": true
    }
  },
  "summary": {
    "total_variables": 8,
    "set_variables": 3,
    "required_variables": 0,
    "sensitive_variables": 2
  }
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/config/environment'
```

---

### 15. Configure Apigee (Unified)
**POST** `/api/config/apigee`

**Description:** Configure and verify connection to Apigee Edge or Apigee X using unified payload structure.

**Request Body:** `ApigeeConfigRequest`
```json
{
  "gateway_type": "Edge",
  "organization": "my-org",
  "login_url": "https://api.enterprise.apigee.com",
  "username": "admin@example.com",
  "password": "password123",
  "environment": "prod"
}
```

**For Apigee X:**
```json
{
  "gateway_type": "X",
  "organization": "apigeex-sandboxmy-org",
  "login_url": "https://apigee.googleapis.com",
  "username": "apigee-z-sandbox@example.com",
  "accessToken": "ya29.xxx...",
  "environment": "apigeex-sandbox"
}
```

**Response:** `ApigeeConfigResponse`
```json
{
  "success": true,
  "message": "Apigee Edge configuration stored successfully (verification skipped)",
  "apigee_type": "Edge",
  "organization": "my-org",
  "org_id": "my-org",
  "environment": "prod",
  "base_url": "https://api.enterprise.apigee.com",
  "verified_at": "2024-01-01T00:00:00Z",
  "stored": true
}
```

**Error Responses:**
- `400`: Invalid request data
- `401`: Authentication failed
- `503`: Service unavailable (network issues)

**cURL (Edge):**
```bash
curl --location 'http://localhost:8080/api/config/apigee' \
  --header 'Content-Type: application/json' \
  --data '{
    "gateway_type": "Edge",
    "organization": "sandbox",
    "login_url": "https://api.enterprise.apigee.com",
    "username": "admin@example.com",
    "password": "password123",
    "environment": "prod"
  }'
```

**cURL (X):**
```bash
curl --location 'http://localhost:8080/api/config/apigee' \
  --header 'Content-Type: application/json' \
  --data '{
    "gateway_type": "X",
    "organization": "apigeex-sandboxmy-org",
    "login_url": "https://apigee.googleapis.com",
    "username": "apigee-z-sandbox@example.com",
    "accessToken": "ya29.xxx...",
    "environment": "apigeex-sandbox"
  }'
```

---

### 16. Get Apigee Configuration
**GET** `/api/config/apigee`

**Description:** Get saved Apigee configuration (without sensitive credentials).

**Query Parameters:**
- `apigee_type` (string, optional): Filter by type ("Edge" or "X")

**Response:**
```json
{
  "configured": true,
  "gateway_type": "Edge",
  "organization": "my-org",
  "login_url": "https://api.enterprise.apigee.com",
  "username": "admin@example.com",
  "environment": "prod",
  "password_masked": "****",
  "verified": false,
  "verified_at": "2024-01-01T00:00:00Z",
  "created_at": "2024-01-01T00:00:00Z"
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/config/apigee'
curl --location 'http://localhost:8080/api/config/apigee?apigee_type=Edge'
```

---

### 17. Configure Apigee X (Legacy)
**POST** `/api/config/apigee-x`

**Description:** Save Apigee X configuration (legacy endpoint).

**Request Body:**
```json
{
  "apigeex_org_name": "my-org",
  "apigeex_token": "ya29.xxx...",
  "apigeex_env": "prod",
  "apigeex_mgmt_url": "https://apigee.googleapis.com/v1/organizations/",
  "folder_name": "/path/to/data_edge"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration saved and verified successfully",
  "config": {
    "org_name": "my-org",
    "env": "prod"
  }
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/config/apigee-x' \
  --header 'Content-Type: application/json' \
  --data '{
    "apigeex_org_name": "my-org",
    "apigeex_token": "ya29.xxx...",
    "apigeex_env": "prod"
  }'
```

---

### 18. Get Apigee X Configuration (Legacy)
**GET** `/api/config/apigee-x`

**Description:** Get saved Apigee X configuration (without sensitive token).

**Request:** None

**Response:**
```json
{
  "configured": true,
  "org_name": "my-org",
  "env": "prod",
  "mgmt_url": "https://apigee.googleapis.com/v1/organizations/",
  "token_preview": "ya29.xxx..."
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/config/apigee-x'
```

---

### 19. Verify Apigee X Credentials
**POST** `/api/config/verify`

**Description:** Verify Apigee X credentials without saving.

**Request Body:**
```json
{
  "apigeex_org_name": "my-org",
  "apigeex_token": "ya29.xxx...",
  "apigeex_env": "prod",
  "apigeex_mgmt_url": "https://apigee.googleapis.com/v1/organizations/"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Credentials verified successfully"
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/config/verify' \
  --header 'Content-Type: application/json' \
  --data '{
    "apigeex_org_name": "my-org",
    "apigeex_token": "ya29.xxx...",
    "apigeex_env": "prod"
  }'
```

---

## Assessment & Dependencies

### 20. Assess Resources
**POST** `/api/assess`

**Description:** Perform migration assessment with dependency analysis.

**Request:** None

**Response:**
```json
{
  "success": true,
  "assessment": {
    "proxy_assessments": [...],
    "shared_flow_assessments": [...],
    "target_server_assessments": [...],
    "kvm_assessments": [...],
    "api_product_assessments": [...],
    "developer_assessments": [...],
    "dependencies": {...},
    "migration_order": [...]
  }
}
```

**cURL:**
```bash
curl --location --request POST 'http://localhost:8080/api/assess'
```

---

### 21. Get Dependencies
**GET** `/api/dependencies`

**Description:** Get dependency graph for all resources.

**Request:** None

**Response:**
```json
{
  "success": true,
  "dependencies": {
    "proxies": {
      "proxy1": ["sharedflow1", "targetserver1"]
    },
    ...
  },
  "migration_order": [
    ["targetserver1", "targetserver2"],
    ["sharedflow1"],
    ["proxy1", "proxy2"]
  ]
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/dependencies'
```

---

## Migration Operations

### 22. Migrate Single Resource
**POST** `/api/migrate/resource`

**Description:** Migrate a single resource using real Apigee X APIs.

**Request Body:**
```json
{
  "resource_type": "proxy",
  "resource_name": "my-proxy",
  "scope": "env",
  "apigee_x_config": {
    "apigeex_org_name": "my-org",
    "apigeex_token": "ya29.xxx...",
    "apigeex_env": "prod",
    "apigeex_mgmt_url": "https://apigee.googleapis.com/v1/organizations/"
  }
}
```

**Supported Resource Types:**
- `proxy` / `proxies`
- `shared_flow` / `sharedflow` / `shared_flows`
- `target_server` / `targetserver` / `target_servers`
- `kvm` / `kvms`
- `api_product` / `apiproduct` / `api_products`
- `developer` / `developers`
- `app` / `apps`

**Response:**
```json
{
  "success": true,
  "resource_type": "proxy",
  "resource_name": "my-proxy",
  "message": "Migration completed successfully"
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/migrate/resource' \
  --header 'Content-Type: application/json' \
  --data '{
    "resource_type": "proxy",
    "resource_name": "my-proxy",
    "apigee_x_config": {
      "apigeex_org_name": "my-org",
      "apigeex_token": "ya29.xxx...",
      "apigeex_env": "prod"
    }
  }'
```

---

## Mock Data

### 23. Get Mock Resources
**GET** `/api/mock/resources/{resource_type}`

**Description:** Get mock resources of a specific type.

**Path Parameters:**
- `resource_type` (string, required): Resource type (proxies, shared_flows, target_servers, kvms, api_products, developers, developer_apps)

**Response:**
```json
[
  {
    "name": "mock-proxy-1",
    "revision": "1",
    ...
  }
]
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/mock/resources/proxies'
curl --location 'http://localhost:8080/api/mock/resources/shared_flows'
curl --location 'http://localhost:8080/api/mock/resources/target_servers'
```

---

## Diff & Comparison

### 24. Calculate Diff
**POST** `/api/diff/calculate`

**Description:** Calculate differences between Edge and X resources.

**Request Body:**
```json
{
  "edge_resource": {
    "name": "my-proxy",
    "revision": "1",
    ...
  },
  "x_resource": {
    "name": "my-proxy",
    "revision": "1",
    ...
  },
  "resource_type": "proxy",
  "resource_name": "my-proxy"
}
```

**Response:**
```json
{
  "resource_type": "proxy",
  "resource_name": "my-proxy",
  "differences": [
    {
      "field": "policies",
      "edge_value": [...],
      "x_value": [...],
      "type": "modified"
    }
  ],
  "summary": {
    "total_differences": 5,
    "added": 2,
    "removed": 1,
    "modified": 2
  }
}
```

**cURL:**
```bash
curl --location 'http://localhost:8080/api/diff/calculate' \
  --header 'Content-Type: application/json' \
  --data '{
    "edge_resource": {...},
    "x_resource": {...},
    "resource_type": "proxy",
    "resource_name": "my-proxy"
  }'
```

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Error message here"
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication failed: Invalid credentials"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error message"
}
```

### 503 Service Unavailable
```json
{
  "detail": "Service unavailable: Network error"
}
```

