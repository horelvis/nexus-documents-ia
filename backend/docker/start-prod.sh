#!/bin/bash

# Production startup script for Nexus Document Backend
# This script uses the production docker-compose configuration

set -e

echo "🚀 Starting Nexus Document Backend in PRODUCTION mode..."
echo "📦 This mode uses optimized images without volume mounting"
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
docker compose -f docker-compose.prod.yml down

# Build images
echo "🔨 Building production images..."
docker compose -f docker-compose.prod.yml build --no-cache

# Start services
echo "🎯 Starting services in production mode..."
docker compose -f docker-compose.prod.yml up -d

# Show status
echo ""
echo "✅ Production environment started!"
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
echo "   docker compose -f docker-compose.prod.yml logs -f [service-name]"
echo ""
echo "🛑 Stop services with:"
echo "   docker compose -f docker-compose.prod.yml down"