#!/bin/bash
set -e

mkdir -p /data

exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
