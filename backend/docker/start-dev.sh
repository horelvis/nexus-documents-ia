#!/bin/bash

# Development startup script for Nexus Document Backend
# This script uses the default docker-compose configuration with volume mounting

set -e

echo "🚀 Starting Nexus Document Backend in DEVELOPMENT mode..."
echo "📁 This mode mounts your source code as volumes for live reloading"
echo ""

# Check if .env file exists in backend root
if [ ! -f "../.env" ]; then
    echo "❌ Error: .env file not found in backend root directory"
    echo "Please create a .env file in backend/ directory with your configuration"
    echo "You can copy from .env.example: cp ../.env.example ../.env"
    exit 1
fi

# Stop any existing containers
echo "🛑 Stopping any existing containers..."
docker compose down

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
docker compose up -d

# Start the unified worker (using both compose files together)
echo "👷 Starting unified background worker..."
docker compose -f docker-compose.yml -f docker-compose.worker.yml up -d unified-worker

# Wait a bit for Ollama to be ready
echo "⏳ Waiting for Ollama service to be ready..."
sleep 5

# Initialize Ollama models if needed
echo "🤖 Checking Ollama models..."
if ! docker compose exec -T ollama-service ollama list 2>/dev/null | grep -q "all-minilm"; then
    echo "📥 Downloading fast embedding model (all-minilm)..."
    docker compose exec -T ollama-service ollama pull all-minilm:latest || echo "⚠️  Failed to download embedding model. You may need to pull it manually."
else
    echo "✅ Embedding model already present"
fi

if ! docker compose exec -T ollama-service ollama list 2>/dev/null | grep -q "llama3.2"; then
    echo "📥 Downloading LLM model (llama3.2)..."
    docker compose exec -T ollama-service ollama pull llama3.2 || echo "⚠️  Failed to download LLM model. You may need to pull it manually."
else
    echo "✅ LLM model already present"
fi

# Show status
echo ""
echo "✅ Development environment started!"
echo ""
echo "📋 Service URLs:"
echo "   • Main API:          http://localhost:8000"
echo "   • API Docs:          http://localhost:8000/docs"
echo "   • LangChain Service: http://localhost:8001"
echo "   • Langroid Service:  http://localhost:8002"
echo "   • Storage Service:   http://localhost:8003"
echo "   • Ollama Service:    http://localhost:8004"
echo "   • Ollama API:        http://localhost:11434"
echo ""
echo "🗄️  Infrastructure:"
echo "   • PostgreSQL:        localhost:5432"
echo "   • Redis:             localhost:6379"
echo "   • Qdrant:            localhost:6333"
echo ""
echo "📊 View logs with:"
echo "   docker compose logs -f [service-name]"
echo "   docker compose -f docker-compose.worker.yml logs -f unified-worker"
echo ""
echo "🛑 Stop services with:"
echo "   docker compose down"
echo "   docker compose -f docker-compose.worker.yml down"
echo ""
echo "💡 Code changes will automatically reload services!"