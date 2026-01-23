#!/bin/bash

# On-Premise startup script for Nexus Document Backend
# Full stack: PostgreSQL+AGE, Redis, Weaviate, vLLM, weaviate-service, API, KeyCloak
#
# Usage:
#   ./start-onpremise.sh           # Start all services
#   ./start-onpremise.sh --no-gpu  # Start without vLLM (CPU mode)

set -e

NO_GPU=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-gpu)
            NO_GPU=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--no-gpu]"
            echo "  --no-gpu    Start without vLLM GPU service"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

echo "🏢 Starting Nexus Document Backend in ON-PREMISE mode..."
echo ""
echo "📦 Services:"
echo "   • PostgreSQL + Apache AGE (knowledge graph)"
echo "   • Redis (cache)"
echo "   • Weaviate (vector database)"
echo "   • Apache Tika (document extraction)"
if ! $NO_GPU; then
    echo "   • vLLM (GPU inference - Qwen3-4B)"
fi
echo "   • Weaviate Service (RAG + SIL)"
echo "   • Main API (backend)"
echo "   • KeyCloak (OIDC/SSO)"
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found"
    echo "Please create a .env file with your configuration"
    exit 1
fi

# Stop any existing containers
echo "🛑 Stopping any existing containers..."
docker compose -f docker-compose.onpremise.yml down

# Build and start services
echo "🔨 Building and starting services..."
if $NO_GPU; then
    docker compose -f docker-compose.onpremise.yml up -d --build --scale vllm=0
else
    docker compose -f docker-compose.onpremise.yml up -d --build
fi

# Wait for services
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Show status
echo ""
echo "✅ On-Premise environment started!"
echo ""
echo "📋 Service URLs:"
echo "   • Main API:          http://localhost:8000"
echo "   • API Docs:          http://localhost:8000/docs"
echo "   • Weaviate Service:  http://localhost:8007"
echo "   • SIL API Docs:      http://localhost:8007/docs"
if ! $NO_GPU; then
    echo "   • vLLM API:          http://localhost:8001"
fi
echo "   • KeyCloak Admin:    http://localhost:8085 (admin/admin)"
echo ""
echo "🗄️  Infrastructure:"
echo "   • PostgreSQL+AGE:    localhost:5432"
echo "   • Redis:             localhost:6379"
echo "   • Weaviate:          localhost:8080"
echo ""
echo "📊 View logs with:"
echo "   docker compose -f docker-compose.onpremise.yml logs -f api"
echo ""
echo "🔑 Test SSO Login:"
echo "   1. Open http://localhost:3001 (frontend on-premise)"
echo "   2. Login with KeyCloak: admin/admin123 or user/user123"
echo ""
echo "🛑 Stop services with:"
echo "   docker compose -f docker-compose.onpremise.yml down"
echo ""
