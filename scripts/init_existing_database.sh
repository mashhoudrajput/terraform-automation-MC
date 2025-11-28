#!/bin/bash
# Script to manually initialize existing databases
# Usage: ./scripts/init_existing_database.sh <hospital_uuid> <is_sub_hospital>

set -e

HOSPITAL_UUID="$1"
IS_SUB_HOSPITAL="${2:-false}"
VM_NAME="${3:-database-init-vm}"
REGION="${4:-me-central2}"
PROJECT_ID="${5:-lively-synapse-400818}"

if [ -z "$HOSPITAL_UUID" ]; then
    echo "Usage: $0 <hospital_uuid> [is_sub_hospital] [vm_name] [region] [project_id]"
    echo "Example: $0 eaf35f0b-0753-4fa1-a700-7f970c405853 false"
    exit 1
fi

echo "Initializing database for hospital: $HOSPITAL_UUID"
echo "Is Sub-Hospital: $IS_SUB_HOSPITAL"
echo "VM Name: $VM_NAME"
echo "Region: $REGION"
echo ""

UUID_UNDERSCORE=$(echo "$HOSPITAL_UUID" | tr '-' '_')
BUCKET_NAME="${UUID_UNDERSCORE}_private_prod"
INIT_SCRIPT="gs://${BUCKET_NAME}/database-init/${HOSPITAL_UUID}/init.sh"

echo "Bucket: $BUCKET_NAME"
echo "Init Script: $INIT_SCRIPT"
echo ""

echo "Executing initialization script on VM..."
gcloud compute ssh "$VM_NAME" \
    --zone="${REGION}-a" \
    --project="$PROJECT_ID" \
    --command="gsutil cp $INIT_SCRIPT /tmp/init-${HOSPITAL_UUID}.sh && chmod +x /tmp/init-${HOSPITAL_UUID}.sh && sudo /tmp/init-${HOSPITAL_UUID}.sh"

echo ""
echo "✅ Database initialization complete!"
