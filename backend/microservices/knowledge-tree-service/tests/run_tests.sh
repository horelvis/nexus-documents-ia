#!/bin/bash
# =============================================================================
# Run knowledge-tree-service tests
#
# Prerequisites:
#   - FalkorDB running on localhost:6380 (docker compose up falkordb)
#   - pip install pytest pytest-asyncio falkordb[asyncio]
#
# Usage:
#   cd backend/microservices/knowledge-tree-service
#   ./tests/run_tests.sh           # all tests
#   ./tests/run_tests.sh -k client # only client tests
#   ./tests/run_tests.sh -v        # verbose
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SERVICE_DIR"

# Ensure test env vars
export FALKORDB_HOST="${FALKORDB_HOST:-localhost}"
export FALKORDB_PORT="${FALKORDB_PORT:-6380}"
export FALKORDB_GRAPH_NAME="${FALKORDB_GRAPH_NAME:-test_knowledge_graph}"
export RAG_KNOWLEDGE_GRAPH_ENABLED=true
export ACTIVE_SECTOR=legal
export LOG_LEVEL=WARNING
export DATABASE_URL="${DATABASE_URL:-postgresql://nexus_user:nexus_password@localhost:5432/nexus_db}"

echo "Running knowledge-tree-service tests..."
echo "  FalkorDB: ${FALKORDB_HOST}:${FALKORDB_PORT} (graph: ${FALKORDB_GRAPH_NAME})"

python -m pytest tests/ -x --tb=short "$@"
