# Multi-Client Terraform Provisioning API

Enterprise-grade API for automated GCP infrastructure provisioning with per-client isolated state management.

## Features

- **Automated Provisioning**: Cloud SQL, GCS buckets, Secret Manager, VPC networking
- **Isolated State**: Each client has independent Terraform state in GCS
- **Custom Passwords**: Format `medicalcircle<special><number>` (e.g., `medicalcircle@2023`)
- **Secret Manager**: MySQL connection strings stored as `mysql://user:pass@host:port/database`
- **REST API**: Complete CRUD operations for client infrastructure management
- **Auto-Naming**: Database names use sanitized hospital names, all other resources use UUID
- **Sub-Hospital Support**: Register sub-hospitals that share parent infrastructure
- **Automatic Schema**: Database tables created automatically (ClusterDB.sql for main, sn_tables.sql for sub)

## Getting Started

### Clone Repository

```bash
git clone git@github.com:mashhoudrajput/terraform-automation-MC.git
cd terraform-automation-MC
```

### Prerequisites Setup

1. **GCP Service Account Key**
   - Place your service account JSON key as `terraform-sa.json` in the project root
   - Ensure it has all required permissions (see Prerequisites section)

2. **GCS State Bucket**
   ```bash
   gsutil mb -p PROJECT_ID -c STANDARD -l me-central2 gs://medical-circles-terraform-state-files
   gsutil versioning set on gs://medical-circles-terraform-state-files
   ```

3. **Database Init VM**
   - Create a VM named `database-init-vm` in the default VPC
   - VM must have `gcloud` and `gsutil` installed
   - VM must be in the same region as deployments

### Build and Run

```bash
# Build Docker image
./scripts/build.sh

# Start the API container
docker run -d \
  --name terraform-backend-api \
  -p 8000:8000 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/infrastructure:/app/infrastructure:ro" \
  -v "$(pwd)/terraform-sa.json:/app/terraform-sa.json:ro" \
  terraform-backend:latest

# Or use the deploy script
./scripts/deploy.sh

# Check health
curl http://localhost:8000/health
```

### Quick Start Examples

```bash
# Register a main hospital (with UUID)
curl -X POST http://localhost:8000/api/hospitals/register \
  -H 'Content-Type: application/json' \
  -d '{
    "client_name": "City General Hospital",
    "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "environment": "prod",
    "region": "me-central2"
  }'

# Check status
curl http://localhost:8000/api/hospitals/550e8400-e29b-41d4-a716-446655440000/status

# List all hospitals
curl http://localhost:8000/api/hospitals

# Register a sub-hospital (after main hospital completes)
curl -X POST http://localhost:8000/api/hospitals/{parent_uuid}/sub-hospitals/register \
  -H 'Content-Type: application/json' \
  -d '{
    "client_name": "City General - Branch A",
    "client_uuid": "660e8400-e29b-41d4-a716-446655440001",
    "environment": "prod",
    "region": "me-central2"
  }'

# Delete a hospital
curl -X DELETE http://localhost:8000/api/clients/{uuid}
```

### Access Frontend

Open your browser: http://localhost:8000

The frontend provides:
- Hospital registration form (with UUID input)
- Real-time status updates
- Hospital list with delete functionality
- Sub-hospital registration for completed hospitals

## Directory Structure

```
.
├── src/                        # Application code
│   ├── api/                    # FastAPI endpoints & error handling
│   ├── core/                   # Business logic (terraform, database, clients)
│   ├── config/                 # Settings
│   └── models/                 # Pydantic models
├── infrastructure/base/        # Terraform templates
│   ├── main.tf                 # Infrastructure resources
│   ├── variables.tf            # Input variables
│   ├── outputs.tf              # Output definitions
│   ├── scripts/                # Database initialization
│   └── sql/                    # SQL schema files
├── deploy/                     # Docker configuration
├── scripts/                    # Build, deploy, cleanup
├── data/                       # Runtime data (excluded from git)
│   └── deployments/            # Client Terraform workspaces
└── frontend/                   # Web UI
```

## Prerequisites

### Required

1. **GCP Service Account** (`terraform-sa.json`) with roles:
   - Compute Network Admin
   - Cloud SQL Admin
   - Storage Admin
   - Secret Manager Admin
   - Service Networking Admin

2. **GCS State Bucket**: `medical-circles-terraform-state-files`
   ```bash
   gsutil mb -p PROJECT_ID -c STANDARD -l me-central2 gs://medical-circles-terraform-state-files
   gsutil versioning set on gs://medical-circles-terraform-state-files
   gsutil iam ch serviceAccount:SA_EMAIL:roles/storage.objectAdmin gs://medical-circles-terraform-state-files
   ```

3. **Database Init VM**: Existing VM in default VPC for schema initialization

### Setup Commands

```bash
# Grant service account permissions
PROJECT_ID="lively-synapse-400818"
SA_EMAIL="terraform-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/compute.networkAdmin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/servicenetworking.networksAdmin"
```

## API Documentation

Base URL: `http://localhost:8000`

### Health Check

**GET** `/health`

Check API health status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-11-25T10:00:00Z"
}
```

**Status Codes:**
- `200 OK`: API is healthy

---

### Root Endpoint

**GET** `/`

Get API information and available endpoints.

**Response:**
```json
{
  "message": "Multi-Client Terraform Provisioning API",
  "version": "1.0.0",
  "endpoints": {
    "register": "POST /api/hospitals/register",
    "status": "GET /api/hospitals/{uuid}/status",
    "outputs": "GET /api/clients/{uuid}/outputs",
    "list": "GET /api/hospitals"
  }
}
```

---

### Register Hospital/Client

**POST** `/api/hospitals/register`  
**POST** `/api/clients/register`

Register a new hospital/client and provision isolated GCP infrastructure.

**Request Body:**
```json
{
  "client_name": "City General Hospital",
  "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "environment": "prod",
  "region": "me-central2"
}
```

**Request Fields:**
- `client_name` (string, required): Name of the hospital/client (1-100 characters)
- `client_uuid` (string, optional): UUID for the hospital. If not provided, one will be auto-generated
- `environment` (string, optional): Deployment environment - `dev`, `staging`, or `prod` (default: `dev`)
- `region` (string, optional): GCP region for deployment (default: `me-central2`)

**Response:** `201 Created`
```json
{
  "client_uuid": "7f54752e-4b12-4746-8893-afabc3e2af29",
  "job_id": "job-7f54752e",
  "status": "completed",
  "status_url": "/api/clients/7f54752e-4b12-4746-8893-afabc3e2af29/status",
  "created_at": "2025-11-27T10:00:00Z"
}
```

**Response Fields:**
- `client_uuid` (string): Unique identifier for the client
- `job_id` (string): Job identifier for tracking deployment
- `status` (string): Current deployment status - `pending`, `in_progress`, `completed`, `failed`
- `status_url` (string): URL to check deployment status
- `created_at` (datetime): Timestamp of registration

**Status Codes:**
- `201 Created`: Client registered successfully
- `500 Internal Server Error`: Registration failed

**Notes:**
- Deployment runs synchronously and may take 5-10 minutes
- Database tables are automatically created after database provisioning
- Database name = sanitized hospital name (e.g., "City General Hospital" → `city_general_hospital`)
- All other resource names are auto-generated by Terraform based on UUID

---

### Register Sub-Hospital

**POST** `/api/hospitals/{parent_uuid}/sub-hospitals/register`

Register a new sub-hospital under a parent hospital. Sub-hospitals share the parent's Cloud SQL instance but have their own database.

**Path Parameters:**
- `parent_uuid` (string, required): UUID of the parent hospital

**Request Body:**
```json
{
  "client_name": "City General - Branch A",
  "client_uuid": "660e8400-e29b-41d4-a716-446655440001",
  "environment": "prod",
  "region": "me-central2"
}
```

**Request Fields:**
- `client_name` (string, required): Name of the sub-hospital (1-100 characters)
- `client_uuid` (string, optional): UUID for the sub-hospital. If not provided, one will be auto-generated
- `environment` (string, optional): Must match parent's environment
- `region` (string, optional): Must match parent's region

**Response:** `201 Created`
```json
{
  "client_uuid": "660e8400-e29b-41d4-a716-446655440001",
  "job_id": "job-660e8400",
  "status": "completed",
  "status_url": "/api/clients/660e8400-e29b-41d4-a716-446655440001/status",
  "created_at": "2025-11-27T10:00:00Z"
}
```

**Status Codes:**
- `201 Created`: Sub-hospital registered successfully
- `404 Not Found`: Parent hospital not found
- `400 Bad Request`: Parent hospital deployment not completed
- `500 Internal Server Error`: Registration failed

**Notes:**
- Parent hospital must be in `completed` status
- Sub-hospital uses parent's Cloud SQL instance
- Sub-hospital database name = sanitized sub-hospital name
- Only `sn_tables.sql` is executed (not `ClusterDB.sql`)
- Deployment runs synchronously and may take 3-5 minutes

---

### Get Hospital/Client Status

**GET** `/api/hospitals/{hospital_uuid}/status`  
**GET** `/api/clients/{client_uuid}/status`

Get the deployment status and details for a specific hospital/client.

**Path Parameters:**
- `hospital_uuid` / `client_uuid` (string, required): Unique identifier of the hospital/client

**Response:** `200 OK`
```json
{
  "client_uuid": "7f54752e-4b12-4746-8893-afabc3e2af29",
  "client_name": "City General Hospital",
  "job_id": "job-7f54752e",
  "status": "completed",
  "environment": "prod",
  "region": "me-central2",
  "created_at": "2025-11-27T10:00:00Z",
  "updated_at": "2025-11-27T10:10:00Z",
  "error_message": null,
  "terraform_outputs": {
    "db_instance_name": "mc-cluster-7f54752e-4b12-4746-8893-afabc3e2af29",
    "db_private_ip": "10.7.1.23",
    "db_port": "3306",
    "database_name": "cluster_7f54752e_4b12_4746_8893_afabc3e2af29",
    "db_username": "dbadmin",
    "connection_uri": "mysql://dbadmin:medicalcircle@2023@10.7.1.23:3306/cluster_7f54752e_4b12_4746_8893_afabc3e2af29",
    "private_bucket_name": "7f54752e_4b12_4746_8893_afabc3e2af29_private_prod",
    "public_bucket_name": "7f54752e_4b12_4746_8893_afabc3e2af29_public_prod",
    "secret_name": "7f54752e_4b12_4746_8893_afabc3e2af29_DATABASE_URI",
    "cluster_id": "7f54752e-4b12-4746-8893-afabc3e2af29",
    "environment": "prod",
    "deployment_region": "me-central2"
  }
}
```

**Response Fields:**
- `client_uuid` (string): Unique identifier for the client
- `client_name` (string): Name of the client
- `job_id` (string): Job identifier
- `status` (string): Deployment status - `pending`, `in_progress`, `completed`, `failed`
- `environment` (string): Deployment environment
- `region` (string): GCP region
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp
- `error_message` (string, nullable): Error message if deployment failed
- `terraform_outputs` (object, nullable): Terraform outputs (only available when status is `completed`)

**Terraform Outputs Fields:**
- `db_instance_name` (string): Cloud SQL instance name
- `db_private_ip` (string): Private IP address of the database
- `db_port` (string): MySQL port number
- `database_name` (string): Database name
- `db_username` (string): Database username
- `connection_uri` (string): Full MySQL connection URI (sensitive)
- `private_bucket_name` (string): Private GCS bucket name
- `public_bucket_name` (string): Public GCS bucket name
- `secret_name` (string): Secret Manager secret name
- `cluster_id` (string): Cluster UUID
- `environment` (string): Deployment environment
- `deployment_region` (string): GCP region

**Status Codes:**
- `200 OK`: Status retrieved successfully
- `404 Not Found`: Client not found

---

### Get Client Outputs

**GET** `/api/clients/{client_uuid}/outputs`

Get detailed Terraform outputs for a specific client. Only available after deployment is completed.

**Path Parameters:**
- `client_uuid` (string, required): Unique identifier of the client

**Response:** `200 OK`
```json
{
  "db_instance_name": "mc-cluster-7f54752e-4b12-4746-8893-afabc3e2af29",
  "db_private_ip": "10.7.1.23",
  "db_port": "3306",
  "database_name": "cluster_7f54752e_4b12_4746_8893_afabc3e2af29",
  "db_username": "dbadmin",
  "connection_uri": "mysql://dbadmin:medicalcircle@2023@10.7.1.23:3306/cluster_7f54752e_4b12_4746_8893_afabc3e2af29",
  "private_bucket_name": "7f54752e_4b12_4746_8893_afabc3e2af29_private_prod",
  "public_bucket_name": "7f54752e_4b12_4746_8893_afabc3e2af29_public_prod",
  "secret_name": "7f54752e_4b12_4746_8893_afabc3e2af29_DATABASE_URI",
  "cluster_id": "7f54752e-4b12-4746-8893-afabc3e2af29",
  "environment": "prod",
  "deployment_region": "me-central2"
}
```

**Status Codes:**
- `200 OK`: Outputs retrieved successfully
- `400 Bad Request`: Deployment not completed
- `404 Not Found`: Client not found or no outputs available

---

### List Hospitals/Clients

**GET** `/api/hospitals`  
**GET** `/api/clients`

List all registered hospitals/clients with their current status.

**Response:** `200 OK`
```json
{
  "clients": [
    {
      "client_uuid": "7f54752e-4b12-4746-8893-afabc3e2af29",
      "client_name": "City General Hospital",
      "status": "completed",
      "environment": "prod",
      "region": "me-central2",
      "created_at": "2025-11-27T10:00:00Z"
    },
    {
      "client_uuid": "ec439ee7-8a50-4003-89e1-4520ceb0f7ca",
      "client_name": "Mashhoud Hospital",
      "status": "completed",
      "environment": "prod",
      "region": "me-central2",
      "created_at": "2025-11-26T13:01:42Z"
    }
  ],
  "total": 2
}
```

**Response Fields:**
- `clients` (array): List of client items
  - `client_uuid` (string): Unique identifier
  - `client_name` (string): Client name
  - `status` (string): Deployment status
  - `environment` (string): Deployment environment
  - `region` (string): GCP region
  - `created_at` (datetime): Creation timestamp
- `total` (integer): Total number of clients

**Status Codes:**
- `200 OK`: List retrieved successfully

---

### Delete Client

**DELETE** `/api/clients/{client_uuid}`

Delete a client and destroy all associated infrastructure.

**Path Parameters:**
- `client_uuid` (string, required): Unique identifier of the client

**Query Parameters:**
- `skip_infrastructure` (boolean, optional): If `true`, skip infrastructure destruction and only delete database record (default: `false`)

**Example:**
```bash
DELETE /api/clients/7f54752e-4b12-4746-8893-afabc3e2af29
DELETE /api/clients/7f54752e-4b12-4746-8893-afabc3e2af29?skip_infrastructure=true
```

**Response:** `200 OK`
```json
{
  "message": "Client 7f54752e-4b12-4746-8893-afabc3e2af29 deleted successfully",
  "client_uuid": "7f54752e-4b12-4746-8893-afabc3e2af29",
  "infrastructure_destroyed": true
}
```

**Response Fields:**
- `message` (string): Success message
- `client_uuid` (string): Deleted client UUID
- `infrastructure_destroyed` (boolean): Whether infrastructure was destroyed

**Status Codes:**
- `200 OK`: Client deleted successfully
- `404 Not Found`: Client not found
- `500 Internal Server Error`: Infrastructure destruction failed

**Notes:**
- Destruction process may take 5-10 minutes
- If infrastructure destruction fails for a client with status `failed`, the database record will still be deleted
- All Terraform-managed resources (Cloud SQL, GCS buckets, Secret Manager secrets) are destroyed

---

## Infrastructure Per Client

Each client deployment creates:

### Cloud SQL MySQL 8.0
- **Instance Name**: `mc-cluster-<cluster_uuid>`
- **Database Name**: `<sanitized_hospital_name>` (e.g., `mashhoud_hospital`, `city_general_hospital`)
- **Version**: MySQL 8.0
- **Tier**: db-f1-micro
- **Network**: Private IP only
- **Backups**: Automatic daily backups at 03:00 UTC
- **Retention**: 7 backups retained
- **Maintenance**: Sunday at 02:00 UTC
- **Tables**: Automatically created via `ClusterDB.sql` + `sn_tables.sql` for main hospitals

### Storage Buckets
- **Private Bucket**: `<cluster_uuid>_private_<environment>` (with underscores)
- **Public Bucket**: `<cluster_uuid>_public_<environment>` (with underscores)
- **Versioning**: Enabled on private bucket
- **Lifecycle**: Old versions deleted after 365 days

### Secret Manager
- **Secret Name**: `<cluster_uuid>_DATABASE_URI` (with underscores)
- **Format**: `mysql://username:password@host:port/database`
- **Example**: `mysql://dbadmin:medicalcircle@2023@10.7.1.23:3306/cluster_7f54752e_4b12_4746_8893_afabc3e2af29`

### Networking
- **Firewall Rules**: MySQL access from internal VPC
- **VPC Peering**: Service networking connection
- **Private IP**: Reserved global address

### Database Initialization
- **Automated**: SQL scripts uploaded to private bucket
- **Location**: `gs://<private_bucket>/database-init/<cluster_uuid>/`
- **Scripts**: `ClusterDB.sql`, `sn_tables.sql`, `init.sh`

## Naming Conventions

All resource names are auto-generated by Terraform:

| Resource Type | Format | Example |
|--------------|--------|---------|
| Cloud SQL Instance | `mc-cluster-<cluster_uuid>` | `mc-cluster-7f54752e-4b12-4746-8893-afabc3e2af29` |
| Database | `<sanitized_hospital_name>` | `mashhoud_hospital`, `city_general_hospital` |
| Secret Manager | `<cluster_uuid>_DATABASE_URI` | `7f54752e_4b12_4746_8893_afabc3e2af29_DATABASE_URI` |
| Private Bucket | `<cluster_uuid>_private_<environment>` | `7f54752e_4b12_4746_8893_afabc3e2af29_private_prod` |
| Public Bucket | `<cluster_uuid>_public_<environment>` | `7f54752e_4b12_4746_8893_afabc3e2af29_public_prod` |
| State File | `<cluster_uuid>/default.tfstate` | `7f54752e_4b12_4746_8893_afabc3e2af29/default.tfstate` |

**Database Name Sanitization:**
- Converted to lowercase
- Spaces, hyphens, dots, slashes → underscores
- Example: "City General Hospital" → `city_general_hospital`
- Example: "Mashhoud Hospital" → `mashhoud_hospital`

**Note**: UUIDs are converted to underscores for resources that require underscore format (secret, buckets, state).

## Password Format

Database passwords follow a fixed format:
- **Pattern**: `medicalcircle<special_character><number>`
- **Special Characters**: `@`, `#`, `$`, `%`, `&`, `*`, `!`, `-`, `_`
- **Number Range**: 1000-9999
- **Examples**: 
  - `medicalcircle@2023`
  - `medicalcircle#4567`
  - `medicalcircle$1234`

## State Management

All Terraform states stored in GCS:
```
medical-circles-terraform-state-files/
├── 7f54752e_4b12_4746_8893_afabc3e2af29/
│   └── default.tfstate
├── ec439ee7_8a50_4003_89e1_4520ceb0f7ca/
│   └── default.tfstate
└── ...
```

**Benefits:**
- Centralized storage
- State locking
- Version history
- Team collaboration

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common Status Codes:**
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

**Example Error Response:**
```json
{
  "detail": "Client not found: 7f54752e-4b12-4746-8893-afabc3e2af29"
}
```

## How to Run

### Option 1: Docker (Recommended)

```bash
# 1. Build the Docker image
./scripts/build.sh

# 2. Start the container
docker run -d \
  --name terraform-backend-api \
  -p 8000:8000 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/infrastructure:/app/infrastructure:ro" \
  -v "$(pwd)/terraform-sa.json:/app/terraform-sa.json:ro" \
  terraform-backend:latest

# 3. Check if running
docker ps | grep terraform-backend-api

# 4. View logs
docker logs -f terraform-backend-api

# 5. Stop the container
docker stop terraform-backend-api
docker rm terraform-backend-api
```

### Option 2: Local Development

```bash
# 1. Install dependencies
cd src
pip install -r requirements.txt

# 2. Set environment variables (optional)
export GCP_PROJECT_ID="lively-synapse-400818"
export GCP_REGION="me-central2"
export STATE_BUCKET_NAME="medical-circles-terraform-state-files"

# 3. Run the API
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Access API
# - API: http://localhost:8000
# - Docs: http://localhost:8000/docs
# - Frontend: http://localhost:8000
```

### Option 3: Using Deploy Script

```bash
# Build and deploy in one command
./scripts/deploy.sh

# This script:
# 1. Builds the Docker image
# 2. Stops any existing container
# 3. Starts a new container
# 4. Shows health status
```

## Development

```bash
# Local development
cd src && pip install -r requirements.txt
python -m uvicorn src.api.main:app --reload

# Docker development
./scripts/build.sh
docker run -d --name terraform-backend-api -p 8000:8000 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/infrastructure:/app/infrastructure:ro" \
  -v "$(pwd)/terraform-sa.json:/app/terraform-sa.json:ro" \
  terraform-backend:latest

# Run tests
pytest tests/

# View logs
docker logs terraform-backend-api

# Cleanup
./scripts/cleanup.sh
```

## Configuration

Environment variables (optional):
```bash
GCP_PROJECT_ID=lively-synapse-400818
GCP_REGION=me-central2
STATE_BUCKET_NAME=medical-circles-terraform-state-files
```

## Database Initialization

### Automatic Initialization

Database tables are **automatically created** during hospital registration:
- **Main Hospitals**: `ClusterDB.sql` + `sn_tables.sql`
- **Sub-Hospitals**: `sn_tables.sql` only

The initialization script runs automatically via `null_resource` after database creation.

### Manual Initialization (for existing databases)

If you have existing databases without tables, use the helper script:

```bash
# Initialize an existing database
./scripts/init_existing_database.sh <hospital_uuid> [is_sub_hospital] [vm_name] [region] [project_id]

# Example
./scripts/init_existing_database.sh 550e8400-e29b-41d4-a716-446655440000 false
```

Or manually:

```bash
# Get init command from outputs
curl http://localhost:8000/api/clients/{uuid}/outputs | jq -r '.database_init_command'

# Execute on your init VM
gcloud compute ssh database-init-vm --zone=me-central2-a \
  --command='gsutil cp gs://BUCKET/database-init/UUID/init.sh /tmp/ && chmod +x /tmp/init.sh && sudo /tmp/init.sh'
```

## Troubleshooting

### Permission Errors
Grant required GCP roles (see Prerequisites section)

### State Lock
```bash
# Check lock files
gsutil ls gs://medical-circles-terraform-state-files/{uuid}/

# Remove stale lock (use with caution)
gsutil rm gs://medical-circles-terraform-state-files/{uuid}/default.tflock
```

### Deployment Failures
Check logs: `docker logs terraform-backend-api`  
View Terraform logs: `cat data/deployments/{uuid}/apply.log`

## Production Deployment

1. Use PostgreSQL instead of SQLite
2. Implement authentication & rate limiting
3. Enable GCP monitoring & alerting
4. Configure backup strategy
5. Set up log aggregation
6. Use production-grade machine types
7. Enable deletion protection

## API Documentation

Interactive docs: http://localhost:8000/docs  
OpenAPI spec: http://localhost:8000/openapi.json

## Git Workflow

### Initial Setup

```bash
# Clone the repository
git clone git@github.com:mashhoudrajput/terraform-automation-MC.git
cd terraform-automation-MC

# Verify remote
git remote -v
```

### Making Changes

```bash
# Check status
git status

# Stage changes
git add .

# Commit with descriptive message
git commit -m "feat: Add new feature description"

# Push to GitHub
git push origin main
```

### Pulling Updates

```bash
# Fetch and merge latest changes
git pull origin main

# Or fetch first, then merge
git fetch origin
git merge origin/main
```

### Branching (Optional)

```bash
# Create a new branch
git checkout -b feature/new-feature

# Make changes and commit
git add .
git commit -m "feat: New feature"

# Push branch
git push -u origin feature/new-feature

# Merge to main (on GitHub or locally)
git checkout main
git merge feature/new-feature
git push origin main
```

## Support

- Health Check: `GET /health`
- API Info: `GET /`
- API Docs: http://localhost:8000/docs
- Frontend: http://localhost:8000
- Logs: `docker logs terraform-backend-api`
- State Files: `data/deployments/{uuid}/`
- GitHub: https://github.com/mashhoudrajput/terraform-automation-MC
