#!/bin/bash
set -e

cd "$(dirname "$0")/../deploy"

docker-compose down
docker-compose up -d

echo "Waiting for health check..."
sleep 5

if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "Deployment successful"
    docker-compose logs --tail=20
else
    echo "Health check failed"
    docker-compose logs
    exit 1
fi

