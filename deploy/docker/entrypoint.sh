#!/bin/bash
set -e

mkdir -p /data

# Set Google Application Credentials if terraform-sa.json exists
if [ -f /app/terraform-sa.json ]; then
    export GOOGLE_APPLICATION_CREDENTIALS=/app/terraform-sa.json
    echo "Set GOOGLE_APPLICATION_CREDENTIALS to /app/terraform-sa.json"
    
    # Authenticate gcloud with service account
    gcloud auth activate-service-account --key-file=/app/terraform-sa.json --quiet || true
    echo "Authenticated gcloud with service account"
fi

exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
