#!/bin/bash
set -e

cd "$(dirname "$0")/.."

DEPLOYMENTS_DIR="./data/deployments"
CONTAINER_NAME="terraform-backend-api"
STATE_BUCKET="medical-circles-terraform-state-files"

echo "====================================="
echo "Terraform Resources Cleanup"
echo "====================================="
echo ""
echo "Note: State files are stored in GCS:"
echo "  gs://$STATE_BUCKET/clients/{uuid}/"
echo ""

if [ ! -d "$DEPLOYMENTS_DIR" ]; then
    echo "No deployments directory found"
    exit 0
fi

for client_dir in "$DEPLOYMENTS_DIR"/*; do
    if [ -d "$client_dir" ]; then
        CLIENT_UUID=$(basename "$client_dir")
        echo "Client: $CLIENT_UUID"
        
        if [ -f "$client_dir/terraform.tfstate" ]; then
            echo "  Checking state..."
            RESOURCES=$(grep -c '"type":' "$client_dir/terraform.tfstate" 2>/dev/null || echo "0")
            echo "  Resources in state: $RESOURCES"
            
            if [ "$RESOURCES" -gt "0" ]; then
                echo "  Running terraform destroy..."
                
                # Try to destroy using docker container
                if docker ps | grep -q "$CONTAINER_NAME"; then
                    docker exec "$CONTAINER_NAME" terraform -chdir="/data/deployments/$CLIENT_UUID" state rm google_secret_manager_secret_version.db_uri 2>/dev/null || true
                    docker exec "$CONTAINER_NAME" terraform -chdir="/data/deployments/$CLIENT_UUID" destroy -auto-approve
                else
                    echo "  Container not running, attempting local destroy..."
                    terraform -chdir="$client_dir" state rm google_secret_manager_secret_version.db_uri 2>/dev/null || true
                    terraform -chdir="$client_dir" destroy -auto-approve -lock=false
                fi
                
                echo "  Destroy complete"
            else
                echo "  No resources to destroy"
            fi
            
            # Remove deployment directory
            if docker ps | grep -q "$CONTAINER_NAME"; then
                docker exec "$CONTAINER_NAME" rm -rf "/data/deployments/$CLIENT_UUID"
                echo "  Directory cleaned"
            fi
        else
            echo "  No state file found"
        fi
        
        echo ""
    fi
done

echo "====================================="
echo "Cleanup complete"
echo "====================================="
echo ""
echo "GCS State Files:"
echo "  Location: gs://$STATE_BUCKET/clients/"
echo ""
echo "To clean up GCS state files (optional):"
echo "  gsutil ls gs://$STATE_BUCKET/clients/"
echo "  gsutil -m rm -r gs://$STATE_BUCKET/clients/{client-uuid}/"
echo ""
echo "To clean up ALL GCS state files:"
echo "  gsutil -m rm -r gs://$STATE_BUCKET/clients/**"
echo ""

