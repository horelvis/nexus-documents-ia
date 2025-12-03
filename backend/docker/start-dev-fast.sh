#!/bin/bash

# Fast Development startup script for Nexus Document Backend
# This script uses volume mounting for instant code changes without rebuilds

set -e

echo "🚀 Starting Nexus Document Backend in FAST DEVELOPMENT mode..."
echo "📁 This mode uses volume mounting for instant code changes"
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
docker compose -f docker-compose.dev.yml down

# Check if images need to be built (only if critical files changed)
echo "🔍 Checking if images need to be rebuilt..."
DOCKERFILE_CHANGED=$(find .. -name "Dockerfile" -newer .docker_dev_built 2>/dev/null | wc -l)
REQUIREMENTS_CHANGED=$(find .. -name "requirements.txt" -newer .docker_dev_built 2>/dev/null | wc -l)
PYPROJECT_CHANGED=$(find .. -name "pyproject.toml" -newer .docker_dev_built 2>/dev/null | wc -l)

if [ ! -f .docker_dev_built ] || [ "$DOCKERFILE_CHANGED" -gt 0 ] || [ "$REQUIREMENTS_CHANGED" -gt 0 ] || [ "$PYPROJECT_CHANGED" -gt 0 ]; then
    echo "🔨 Building development images with volume mounting..."
    docker compose -f docker-compose.dev.yml build
    touch .docker_dev_built
    echo "✅ Development images built with volume support"
else
    echo "✅ Development images are up to date, using cached versions"
fi

# Start services with volume mounting
echo "🎯 Starting services with live code reloading..."
docker compose -f docker-compose.dev.yml up -d

# Start the background worker microservice
echo "👷 Starting background-worker service..."
docker compose -f docker-compose.dev.yml up -d background-worker

# Wait a bit for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Initialize Ollama models if needed
echo "🤖 Checking Ollama models..."
if ! docker compose -f docker-compose.dev.yml exec -T genai-ollama ollama list 2>/dev/null | grep -q "all-minilm"; then
    echo "📥 Downloading fast embedding model (all-minilm)..."
    docker compose -f docker-compose.dev.yml exec -T genai-ollama ollama pull all-minilm:latest || echo "⚠️  Failed to download embedding model. You may need to pull it manually."
else
    echo "✅ Embedding model already present"
fi

if ! docker compose -f docker-compose.dev.yml exec -T genai-ollama ollama list 2>/dev/null | grep -q "llama3.2"; then
    echo "📥 Downloading LLM model (llama3.2)..."
    docker compose -f docker-compose.dev.yml exec -T genai-ollama ollama pull llama3.2 || echo "⚠️  Failed to download LLM model. You may need to pull it manually."
else
    echo "✅ LLM model already present"
fi

# Show status
echo ""
echo "✅ Fast Development environment started!"
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
echo "   • Weaviate:          localhost:8080"
echo "   • Elasticsearch:     localhost:9200"
echo ""
echo "📊 View logs with:"
echo "   docker compose -f docker-compose.dev.yml logs -f [service-name]"
echo "   docker compose -f docker-compose.dev.yml logs -f background-worker"
echo ""
echo "🛑 Stop services with:"
echo "   docker compose -f docker-compose.dev.yml down"
echo ""
echo "💡 Code changes will automatically reload services!"
echo "⚡ No rebuilds needed - just save your files!"
