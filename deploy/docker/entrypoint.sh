#!/bin/bash
set -e

mkdir -p /data

if [ -f /app/terraform-sa.json ]; then
    export GOOGLE_APPLICATION_CREDENTIALS=/app/terraform-sa.json
    gcloud auth activate-service-account --key-file=/app/terraform-sa.json --quiet || true
fi

exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
