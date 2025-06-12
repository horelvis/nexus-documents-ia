#!/bin/bash

# Start Gotenberg in the background
echo "Starting Gotenberg..."
gotenberg --api-port=3000 --api-timeout=30s --log-level=INFO &

# Wait for Gotenberg to be ready
echo "Waiting for Gotenberg to start..."
sleep 5

# Start the FastAPI application
echo "Starting FastAPI application..."
if [ "${DEBUG:-false}" = "true" ]; then
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
else
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005
fi