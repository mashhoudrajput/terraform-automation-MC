<!-- e5f681ec-3913-4192-b81c-e3cd50d85ba3 be5b6e14-8212-4607-9b5a-d8d154a822b5 -->
# Update Resource Naming Conventions

## Current vs New Naming Patterns

### Current Naming:

- **Secret Manager**: `db-uri-{uuid[:8]}` (e.g., `db-uri-ec439ee7`)
- **Database Name**: `client_{uuid_underscore[:20]}_db` (e.g., `client_ec439ee7_8a50_4003_8_db`)
- **State File Path**: `clients/{uuid}/terraform.tfstate` (e.g., `clients/ec439ee7-8a50-4003-89e1-4520ceb0f7ca/terraform.tfstate`)

### New Naming:

- **Secret Manager**: `{uuid_underscore}_DATABASE_URI` (e.g., `ec439ee7_8a50_4003_89e1_4520ceb0f7ca_DATABASE_URI`)
- **Database Name**: `{uuid_underscore}_mysql` (e.g., `ec439ee7_8a50_4003_89e1_4520ceb0f7ca_mysql`)
- **State File Path**: `{uuid_underscore}/terraform.tfstate` (e.g., `ec439ee7_8a50_4003_89e1_4520ceb0f7ca/terraform.tfstate`)

## Files to Update

### 1. `src/core/terraform_service.py`

- **Line 90**: Update `database_name` in `generate_tfvars()`:
- From: `"client_{client_uuid.replace('-', '_')[:20]}_db"`
- To: `"{client_uuid.replace('-', '_')}_mysql"`

- **Line 110**: Update `secret_name` in `generate_tfvars()`:
- From: `"db-uri-{client_u