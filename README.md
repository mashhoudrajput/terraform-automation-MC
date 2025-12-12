# Multi-Client Terraform Provisioning API

Enterprise-grade API for automated GCP infrastructure provisioning with per-client isolated state management.

## Features

- Automated Provisioning: Cloud SQL, GCS buckets, Secret Manager, VPC networking
- Isolated State: Each client has independent Terraform state in GCS
- Custom Passwords: Random 8-character base64 strings for database access
- Secret Manager: MySQL connection strings stored securely
- REST API: Complete CRUD operations for client infrastructure management
- Auto-Naming: Database names use sanitized hospital names, all other resources use UUID
- Sub-Hospital Support: Register sub-hospitals that share parent infrastructure
- Private Database: Database accessible only via private IP within VPC
- Database Backup: Automatic SQLite backup to GCS every 5 minutes
- Professional Logging: Comprehensive logging for Python and Terraform operations

## Architecture

- Backend: FastAPI (Python 3.11)
- Infrastructure: Terraform with GCS backend
- Database: SQLite with GCS backup
- Deployment: Docker container on Cloud Run
- Authentication: API key-based

## Prerequisites

### Required GCP Resources

1. **GCS State Bucket**
   ```bash
   gsutil mb -p PROJECT_ID -c STANDARD -l me-central2 gs://medical-circles-terraform-state-files
   gsutil versioning set on gs://medical-circles-terraform-state-files
   ```

2. **Service Account Permissions**
   - Compute Network Admin
   - Cloud SQL Admin
   - Storage Admin
   - Secret Manager Admin
   - Service Networking Admin

### Local Development

- Docker
- GCP credentials file (`terraform-sa.json`) - optional for Cloud Run
- Environment variables (see `env.example`)

## Quick Start

### Build and Run Locally

```bash
docker build -t mc-backend -f deploy/docker/Dockerfile .

mkdir -p data
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/terraform-sa.json:/app/terraform-sa.json:ro" \
  -v "$(pwd)/data:/data" \
  mc-backend
```

### Cloud Run Deployment

1. Build and push to Artifact Registry:
   ```bash
   docker build -t me-central2-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:latest -f deploy/docker/Dockerfile .
   docker push me-central2-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:latest
   ```

2. Deploy to Cloud Run with:
   - Service account attached (for GCP permissions)
   - Environment variables from `.env`
   - API key set in environment

## API Usage

### Authentication

All API endpoints require `X-API-Key` header:
```bash
-H 'X-API-Key: your-api-key'
```

### Register Hospital

```bash
curl -X POST http://localhost:8000/api/hospitals/register \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-api-key' \
  -d '{
    "client_name": "City General Hospital",
    "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "environment": "prod",
    "region": "me-central2"
  }'
```

### Check Status

```bash
curl -H 'X-API-Key: your-api-key' \
  http://localhost:8000/api/hospitals/{uuid}/status
```

### List Hospitals

```bash
curl -H 'X-API-Key: your-api-key' \
  http://localhost:8000/api/hospitals
```

### Register Sub-Hospital

```bash
curl -X POST http://localhost:8000/api/hospitals/{parent_uuid}/sub-hospitals/register \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-api-key' \
  -d '{
    "client_name": "City General - Branch A",
    "client_uuid": "660e8400-e29b-41d4-a716-446655440001",
    "environment": "prod",
    "region": "me-central2"
  }'
```

### Delete Hospital

```bash
curl -X DELETE http://localhost:8000/api/clients/{uuid} \
  -H 'X-API-Key: your-api-key'
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/` | Service status |
| GET | `/api` | API information |
| POST | `/api/hospitals/register` | Register new hospital |
| GET | `/api/hospitals/{uuid}/status` | Get hospital status |
| POST | `/api/hospitals/{uuid}/create-tables` | Create database tables |
| POST | `/api/hospitals/{parent_uuid}/sub-hospitals/register` | Register sub-hospital |
| GET | `/api/hospitals` | List all hospitals |
| GET | `/api/clients/{uuid}/status` | Get client status |
| GET | `/api/clients/{uuid}/outputs` | Get Terraform outputs |
| DELETE | `/api/clients/{uuid}` | Delete client |

## Configuration

### Environment Variables

See `env.example` for all available configuration options:

- `API_KEY`: API authentication key
- `GCP_PROJECT_ID`: GCP project ID
- `GCP_REGION`: Default GCP region
- `STATE_BUCKET_NAME`: GCS bucket for Terraform state
- `DATABASE_BACKUP_BUCKET`: GCS bucket for database backups
- `DATABASE_BACKUP_INTERVAL_SECONDS`: Backup interval (default: 300)

### Credentials

The application supports two authentication methods:

1. **File-based** (local development): Place `terraform-sa.json` in project root
2. **Default credentials** (Cloud Run): Attach service account to Cloud Run service

## Infrastructure Per Client

Each deployment creates:

- **Cloud SQL MySQL 8.0**: Private IP only, accessible within VPC
- **Storage Buckets**: Private and public GCS buckets
- **Secret Manager**: Database connection string stored securely
- **Networking**: VPC peering and firewall rules

## State Management

All Terraform states stored in GCS:
```
medical-circles-terraform-state-files/
├── {client_uuid}/
│   └── default.tfstate
```

## Database Backup

- SQLite database automatically backed up to GCS every 5 minutes
- Backup bucket: `medical-circles-terraform-state-files`
- Backup object: `clients.db`
- On startup: Downloads latest snapshot from GCS
- On shutdown: Performs final backup

## Logging

### Python Logging

- Level: INFO
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- All operations logged with context

### Terraform Logging

- All Terraform commands logged to workspace-specific log files:
  - `init.log`: Terraform initialization
  - `apply.log`: Terraform apply operations
  - `destroy.log`: Terraform destroy operations

## Directory Structure

```
.
├── src/
│   ├── api/              # FastAPI application
│   │   ├── routes/       # API route handlers
│   │   ├── middleware/   # Authentication middleware
│   │   └── main.py       # Application entry point
│   ├── core/             # Business logic
│   │   ├── services/     # Database services
│   │   ├── terraform_service.py
│   │   ├── client_service.py
│   │   ├── database.py
│   │   └── db_backup.py
│   ├── config/           # Configuration
│   └── models/           # Pydantic models
├── infrastructure/base/  # Terraform templates
├── deploy/docker/        # Docker configuration
└── env.example           # Environment variables template
```

## Development

### Local Development

```bash
pip install -r src/requirements.txt
API_KEY=... python -m uvicorn src.api.main:app --reload
```

### Docker Development

```bash
docker build -t mc-backend -f deploy/docker/Dockerfile .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/terraform-sa.json:/app/terraform-sa.json:ro" \
  -v "$(pwd)/data:/data" \
  mc-backend
```

## Troubleshooting

### Permission Errors

Ensure service account has required GCP roles (see Prerequisites).

### State Lock

```bash
gsutil ls gs://medical-circles-terraform-state-files/{uuid}/
gsutil rm gs://medical-circles-terraform-state-files/{uuid}/default.tflock
```

### Deployment Failures

Check logs:
- Container logs: `docker logs <container>`
- Terraform logs: `data/deployments/{uuid}/apply.log`
- Application logs: Container stdout/stderr

## Production Considerations

1. Use Cloud SQL PostgreSQL instead of SQLite
2. Implement rate limiting
3. Enable GCP monitoring and alerting
4. Configure backup retention policies
5. Set up log aggregation
6. Use production-grade machine types
7. Enable deletion protection for critical resources

## API Documentation

- Interactive docs: `http://localhost:8000/docs`
- OpenAPI spec: `http://localhost:8000/openapi.json`

## License

Proprietary
