#!/bin/bash

echo "🚀 Starting NexusDocs360 Migration: Qdrant -> Weaviate + Elysia"
echo "================================================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please create one based on .env.example"
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

echo "🔧 Migration Configuration:"
echo "  - MIGRATION_MODE: ${MIGRATION_MODE:-parallel}"
echo "  - ENABLE_WEAVIATE: ${ENABLE_WEAVIATE:-true}"
echo "  - ELYSIA_ENABLED: ${ELYSIA_ENABLED:-true}"
echo ""

# Ensure migration mode is set correctly
export MIGRATION_MODE=${MIGRATION_MODE:-parallel}
export ENABLE_WEAVIATE=${ENABLE_WEAVIATE:-true}
export ELYSIA_ENABLED=${ELYSIA_ENABLED:-true}

echo "📋 Migration Phases:"
echo "  1. PARALLEL: Both Qdrant and Weaviate running (current)"
echo "  2. WEAVIATE_ONLY: Switch to Weaviate only after testing"
echo "  3. CLEANUP: Remove Qdrant containers (manual step)"
echo ""

echo "🐳 Starting Docker containers with migration support..."

# Start all services including the new Weaviate stack
docker-compose up -d --build

echo "⏳ Waiting for services to be healthy..."
sleep 30

echo "🔍 Checking service health..."

# Check main services
echo "  📊 Main API..."
curl -s http://localhost:8000/health > /dev/null && echo "    ✅ API healthy" || echo "    ❌ API unhealthy"

echo "  🗄️ Legacy Qdrant..."
curl -s http://localhost:6333/health > /dev/null && echo "    ✅ Qdrant healthy" || echo "    ❌ Qdrant unhealthy"

echo "  🆕 Weaviate Database..."
curl -s http://localhost:8080/v1/.well-known/ready > /dev/null && echo "    ✅ Weaviate healthy" || echo "    ❌ Weaviate unhealthy"

echo "  🧠 Weaviate Service + Elysia..."
curl -s http://localhost:8007/health > /dev/null && echo "    ✅ Weaviate Service healthy" || echo "    ❌ Weaviate Service unhealthy"

echo "  🤖 CAG Service (CrewAI)..."
curl -s http://localhost:8008/health > /dev/null && echo "    ✅ CAG Service healthy" || echo "    ❌ CAG Service unhealthy"

echo ""
echo "🎯 Migration Status Check..."
curl -s http://localhost:8000/api/v1/migration/status | python3 -m json.tool || echo "❌ Could not get migration status"

echo ""
echo "🌐 Available Services:"
echo "  - Main API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - Migration API: http://localhost:8000/api/v1/migration/"
echo "  - Weaviate: http://localhost:8080"
echo "  - Weaviate Service: http://localhost:8007"
echo "  - Qdrant (legacy): http://localhost:6333"
echo "  - CAG Service: http://localhost:8008"

echo ""
echo "🧠 Advanced Elysia Tools Available:"
echo "  - Contract Analysis: Extracts parties, dates, terms from legal documents"
echo "  - Financial Analysis: Analyzes revenue, profit, and financial metrics"
echo "  - Risk Assessment: Identifies potential risks across documents"
echo "  - Compliance Checking: Validates regulatory compliance"
echo "  - Multi-language Processing: Handles documents in multiple languages"
echo "  - Entity Linking: Connects related entities across documents"
echo "  - Trend Analysis: Identifies patterns over document collections"

echo ""
echo "🔍 Test Advanced Elysia Features:"
echo "  1. Contract Analysis: curl -X POST 'http://localhost:8000/api/v1/migration/search' -H 'Content-Type: application/json' -d '{\"query\":\"analyze contract terms and parties\", \"query_type\":\"analyze\"}'"
echo "  2. Financial Analysis: curl -X POST 'http://localhost:8000/api/v1/migration/search' -H 'Content-Type: application/json' -d '{\"query\":\"financial performance analysis\", \"query_type\":\"analyze\"}'"
echo "  3. Risk Assessment: curl -X POST 'http://localhost:8000/api/v1/migration/search' -H 'Content-Type: application/json' -d '{\"query\":\"identify risks in documents\", \"query_type\":\"analyze\"}'"

echo ""
echo "📚 Migration Steps:"
echo "  1. Test both systems: curl -X POST 'http://localhost:8000/api/v1/migration/compare?query=contract analysis'"
echo "  2. Monitor advanced features: docker-compose logs -f weaviate-service"
echo "  3. Check available tools: curl http://localhost:8000/api/v1/migration/tools"
echo "  4. Test visualizations: Use /api/v1/migration/visualize endpoint"
echo "  5. When ready, set MIGRATION_MODE=weaviate_only in .env and restart"

echo ""
echo "✅ Advanced Elysia Integration Complete!"
echo "🚀 NexusDocs360 now features decision trees, 10+ specialized tools, and intelligent routing!"