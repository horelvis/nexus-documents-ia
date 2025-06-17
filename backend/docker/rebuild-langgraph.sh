#!/bin/bash

echo "Rebuilding LangGraph service..."

# Stop the langgraph service
echo "Stopping langgraph-service..."
docker compose stop langgraph-service

# Remove the old container
echo "Removing old container..."
docker compose rm -f langgraph-service

# Rebuild the image with no cache
echo "Building new image..."
docker compose build --no-cache langgraph-service

# Start the service
echo "Starting langgraph-service..."
docker compose up -d langgraph-service

# Show logs
echo "Showing logs (press Ctrl+C to exit)..."
docker compose logs -f langgraph-service