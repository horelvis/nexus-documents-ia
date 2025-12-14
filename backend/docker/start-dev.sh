#!/bin/bash

# Development startup script for Nexus Document Backend
# This script uses the default docker-compose configuration with volume mounting

set -e

REMOVE_ORPHANS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean-orphans)
            REMOVE_ORPHANS=true
            shift
            ;;
        *)
            echo "Uso: $0 [--clean-orphans]"
            exit 1
            ;;
    esac
done

echo "🚀 Starting Nexus Document Backend in DEVELOPMENT mode..."
echo "📁 This mode mounts your source code as volumes for live reloading"
echo ""
if $REMOVE_ORPHANS; then
    echo "🧹 Orphan containers will be removed during stop/start."
    echo ""
fi

# Check if .env file exists in backend root
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found in backend root directory"
    echo "Please create a .env file in backend/ directory with your configuration"
    echo "You can copy from .env.example: cp ../.env.example ../.env"
    exit 1
fi

# Stop any existing containers
echo "🛑 Stopping any existing containers..."
if $REMOVE_ORPHANS; then
    docker compose down --remove-orphans
else
    docker compose down
fi

# Check if images need to be built (only if Dockerfile or requirements.txt changed)
echo "🔍 Checking if images need to be rebuilt..."
DOCKERFILE_CHANGED=$(find .. -name "Dockerfile" -newer .docker_built 2>/dev/null | wc -l)
REQUIREMENTS_CHANGED=$(find .. -name "requirements.txt" -newer .docker_built 2>/dev/null | wc -l)
PYPROJECT_CHANGED=$(find .. -name "pyproject.toml" -newer .docker_built 2>/dev/null | wc -l)

if [ ! -f .docker_built ] || [ "$DOCKERFILE_CHANGED" -gt 0 ] || [ "$REQUIREMENTS_CHANGED" -gt 0 ] || [ "$PYPROJECT_CHANGED" -gt 0 ]; then
    echo "🔨 Building development images (changes detected)..."
    docker compose build
    touch .docker_built
    echo "✅ Images built and timestamp updated"
else
    echo "✅ Images are up to date, skipping build"
fi

# Start services
echo "🎯 Starting services in development mode..."
if $REMOVE_ORPHANS; then
    docker compose up -d --remove-orphans
else
    docker compose up -d
fi

# Start the background worker microservice
echo "👷 Ensuring background-worker service is running..."
docker compose up -d background-worker

# Wait for vLLM to be ready (if enabled)
if docker compose ps vllm 2>/dev/null | grep -q "Up"; then
    echo "🤖 vLLM service is running (GPU inference)"
fi

# Show status
echo ""
echo "✅ Development environment started!"
echo ""
echo "📋 Service URLs:"
echo "   • Main API:          http://localhost:8000"
echo "   • API Docs:          http://localhost:8000/docs"
echo "   • Storage Service:   http://localhost:8003"
echo "   • Weaviate Service:  http://localhost:8007"
echo "   • Elasticsearch Svc: http://localhost:8008"
echo "   • vLLM API:          http://localhost:8001 (GPU inference)"
echo ""
echo "🗄️  Infrastructure:"
echo "   • PostgreSQL:        localhost:5432"
echo "   • Redis:             localhost:6379"
echo "   • Weaviate:          localhost:8080"
echo "   • Elasticsearch:     localhost:9200"
echo ""
echo "📊 View logs with:"
echo "   docker compose logs -f [service-name]"
echo "   docker compose logs -f weaviate-service"
echo ""
echo "🛑 Stop services with:"
echo "   docker compose down [--remove-orphans]"
echo ""
echo "💡 Code changes will automatically reload services!"
