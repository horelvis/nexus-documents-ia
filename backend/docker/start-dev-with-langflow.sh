#!/bin/bash

# Script to start development environment with Langflow

echo "🚀 Starting Nexus development environment with Langflow..."

# Create necessary directories
mkdir -p langflow/flows langflow/components

# Stop any running containers
echo "🛑 Stopping existing containers..."
docker compose down

# Pull latest Langflow image
echo "📦 Pulling latest Langflow image..."
docker pull langflowai/langflow:latest

# Start only essential services first
echo "🔧 Starting core services..."
docker compose up -d postgres redis qdrant ollama-service

# Wait for services to be ready
echo "⏳ Waiting for core services to be ready..."
sleep 10

# Start Langflow
echo "🎨 Starting Langflow visual agent builder..."
docker compose up -d langflow

# Wait for Langflow to be ready
echo "⏳ Waiting for Langflow to initialize..."
sleep 15

# Start remaining services
echo "🚀 Starting remaining services..."
docker compose up -d

# Show status
echo "✅ All services started!"
echo ""
echo "📍 Service URLs:"
echo "   - Main API: http://localhost:8000/docs"
echo "   - Langflow: http://localhost:7860"
echo "   - LangChain Service: http://localhost:8001/docs"
echo "   - Langroid Service: http://localhost:8002/docs"
echo "   - Qdrant: http://localhost:6333/dashboard"
echo ""
echo "🎨 Langflow Usage:"
echo "   1. Open http://localhost:7860 in your browser"
echo "   2. Create new flows or import from ./langflow/flows/"
echo "   3. Export flows as JSON to import into the system"
echo "   4. Flows are persisted in ./langflow/flows/"
echo ""
echo "💡 Tips:"
echo "   - Langflow is connected to local Ollama (llama3.2)"
echo "   - Use QdrantVectorStore nodes for RAG capabilities"
echo "   - Export flows and import via API or Admin UI"
echo ""

# Follow logs
echo "📋 Following logs (Ctrl+C to exit)..."
docker compose logs -f langflow