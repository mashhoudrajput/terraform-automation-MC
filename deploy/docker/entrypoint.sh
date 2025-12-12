#!/bin/bash
set -e

mkdir -p /data

if [ -f /app/terraform-sa.json ]; then
    export GOOGLE_APPLICATION_CREDENTIALS=/app/terraform-sa.json
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: Set GOOGLE_APPLICATION_CREDENTIALS to /app/terraform-sa.json"
    
    gcloud auth activate-service-account --key-file=/app/terraform-sa.json --quiet || true
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: Authenticated gcloud with service account"
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: No credentials file found. Using default credentials (Cloud Run service account)"
fi

echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: Starting application server"
exec python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --log-level info
