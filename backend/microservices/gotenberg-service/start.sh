#!/bin/bash

# Start Gotenberg in the background
echo "Starting Gotenberg..."
gotenberg --api-port=3000 --api-timeout=30s --log-level=WARN &

# Wait for Gotenberg to be ready
echo "Waiting for Gotenberg to start..."
sleep 5

# Activate virtual environment
source /opt/venv/bin/activate

# Start the FastAPI application
echo "Starting FastAPI application..."
uvicorn app.main:app --host 0.0.0.0 --port 8005