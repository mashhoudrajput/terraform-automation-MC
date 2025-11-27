#!/bin/bash
# Quick script to initialize existing databases
# Usage: ./scripts/init_databases.sh

set -e

VM_NAME="${1:-db-init-cluster-001-dev}"
ZONE="${2:-me-central2-a}"
PROJECT_ID="${3:-lively-synapse-400818}"
API_URL="${4:-http://localhost:8000}"

echo "=== Database Initialization Helper ==="
echo "VM: $VM_NAME"
echo "Zone: $ZONE"
echo "Project: $PROJECT_ID"
echo ""

# Get all hospitals
HOSPITALS=$(curl -s "$API_URL/api/hospitals" | jq -r '.clients[] | "\(.client_uuid)|\(.client_name)|\(.parent_uuid // "none")"')

echo "Found hospitals:"
echo "$HOSPITALS" | while IFS='|' read -r uuid name parent; do
  if [ -n "$uuid" ]; then
    echo "  - $name (UUID: $uuid)"
  fi
done

echo ""
echo "Initializing databases..."

echo "$HOSPITALS" | while IFS='|' read -r uuid name parent; do
  if [ -z "$uuid" ]; then
    continue
  fi
  
  echo ""
  echo "Processing: $name"
  
  if [ "$parent" = "none" ]; then
    # Main hospital
    BUCKET=$(curl -s "$API_URL/api/clients/$uuid/outputs" 2>/dev/null | jq -r '.private_bucket_name // empty')
    if [ -z "$BUCKET" ]; then
      echo "  No outputs available, skipping..."
      continue
    fi
    
    echo "  Bucket: $BUCKET"
    echo "  Running initialization..."
    
    gcloud compute ssh "$VM_NAME" \
      --zone="$ZONE" \
      --project="$PROJECT_ID" \
      --command="gsutil cp gs://$BUCKET/database-init/$uuid/init.sh /tmp/init-$uuid.sh && chmod +x /tmp/init-$uuid.sh && sudo /tmp/init-$uuid.sh" || echo "  ❌ Failed"
    
  else
    # Sub-hospital - use parent's bucket
    PARENT_BUCKET=$(curl -s "$API_URL/api/clients/$parent/outputs" 2>/dev/null | jq -r '.private_bucket_name // empty')
    if [ -z "$PARENT_BUCKET" ]; then
      echo "  No parent outputs available, skipping..."
      continue
    fi
    
    echo "  Parent Bucket: $PARENT_BUCKET"
    echo "  Running initialization..."
    
    gcloud compute ssh "$VM_NAME" \
      --zone="$ZONE" \
      --project="$PROJECT_ID" \
      --command="gsutil cp gs://$PARENT_BUCKET/database-init/$uuid/init.sh /tmp/init-$uuid.sh && chmod +x /tmp/init-$uuid.sh && sudo /tmp/init-$uuid.sh" || echo "  Failed"
  fi
done

echo ""
echo "Initialization complete!"
echo ""
echo "Verify tables:"
echo "  mysql -h 10.7.1.39 -u dbadmin -p mashhoud_hospital -e 'SHOW TABLES;'"
echo "  mysql -h 10.7.1.39 -u dbadmin -p shafea_hospital -e 'SHOW TABLES;'"

