#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Building Docker image..."
docker build -t terraform-backend:latest -f deploy/docker/Dockerfile .

echo "Build complete: terraform-backend:latest"

