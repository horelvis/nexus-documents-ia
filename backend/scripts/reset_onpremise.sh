#!/bin/bash
#
# Reset On-Premise Single Tenant Environment
#
# This script performs a complete reset of all data stores:
# - PostgreSQL: Drops and recreates database with fresh schema
# - Weaviate: Deletes all collections
# - Redis: Flushes all cached data
# - Elasticsearch: Deletes all indices (if used)
#
# After reset, the system will:
# - Create the default single tenant on first startup
# - Be ready for fresh data import from connectors (Alfresco, etc.)
#
# WARNING: THIS WILL DELETE ALL DATA! Make backups first!
#
# Usage:
#   ./scripts/reset_onpremise.sh [--confirm]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$BACKEND_DIR/docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "============================================================"
echo "  NOUXCUBEIA ON-PREMISE RESET"
echo "  Single Tenant Mode"
echo "============================================================"
echo -e "${NC}"

# Check for confirmation flag
if [[ "$1" != "--confirm" ]]; then
    echo -e "${RED}WARNING: This will DELETE ALL DATA!${NC}"
    echo ""
    echo "This script will:"
    echo "  - Drop and recreate PostgreSQL database"
    echo "  - Delete all Weaviate collections"
    echo "  - Flush Redis cache"
    echo "  - Delete Elasticsearch indices"
    echo ""
    echo -e "${YELLOW}Make sure you have backups before proceeding!${NC}"
    echo ""
    echo "To proceed, run:"
    echo "  $0 --confirm"
    echo ""
    exit 1
fi

echo -e "${YELLOW}Starting reset in 5 seconds... (Ctrl+C to cancel)${NC}"
sleep 5

# Function to check if container is running
container_running() {
    docker ps --format '{{.Names}}' | grep -q "$1"
}

# Function to wait for service to be ready
wait_for_service() {
    local service=$1
    local max_attempts=$2
    local attempt=1

    echo -n "  Waiting for $service"
    while [ $attempt -le $max_attempts ]; do
        if docker exec "$service" echo "ready" &>/dev/null; then
            echo -e " ${GREEN}ready${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    echo -e " ${RED}timeout${NC}"
    return 1
}

# ============================================================
# 1. STOP SERVICES
# ============================================================
echo -e "\n${BLUE}[1/6] Stopping services...${NC}"
cd "$DOCKER_DIR"

# Stop API and workers first (they depend on data stores)
for svc in docker-api-1 docker-weaviate-service-1 docker-background-worker-1; do
    if container_running "$svc"; then
        echo "  Stopping $svc..."
        docker stop "$svc" 2>/dev/null || true
    fi
done

echo -e "  ${GREEN}Services stopped${NC}"

# ============================================================
# 2. RESET POSTGRESQL
# ============================================================
echo -e "\n${BLUE}[2/6] Resetting PostgreSQL...${NC}"

if container_running "docker-db-1"; then
    echo "  Dropping database..."
    docker exec docker-db-1 psql -U nexus_user -d postgres -c "
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = 'nouxcube' AND pid <> pg_backend_pid();
    " 2>/dev/null || true

    docker exec docker-db-1 psql -U nexus_user -d postgres -c "DROP DATABASE IF EXISTS nouxcube;" 2>/dev/null
    docker exec docker-db-1 psql -U nexus_user -d postgres -c "CREATE DATABASE nouxcube OWNER nexus_user;" 2>/dev/null

    echo -e "  ${GREEN}PostgreSQL reset${NC}"
else
    echo -e "  ${YELLOW}PostgreSQL not running, skipping${NC}"
fi

# ============================================================
# 3. RESET WEAVIATE
# ============================================================
echo -e "\n${BLUE}[3/6] Resetting Weaviate...${NC}"

if container_running "docker-weaviate-1"; then
    # Delete all collections via REST API
    echo "  Deleting all collections..."

    # Get list of collections and delete each
    collections=$(docker exec docker-weaviate-1 wget -qO- http://localhost:8080/v1/schema 2>/dev/null | \
        python3 -c "import sys,json; data=json.load(sys.stdin); print(' '.join([c['class'] for c in data.get('classes',[])]))" 2>/dev/null || echo "")

    for collection in $collections; do
        echo "    Deleting $collection..."
        docker exec docker-weaviate-1 wget -qO- --method=DELETE "http://localhost:8080/v1/schema/$collection" 2>/dev/null || true
    done

    echo -e "  ${GREEN}Weaviate reset${NC}"
else
    echo -e "  ${YELLOW}Weaviate not running, skipping${NC}"
fi

# ============================================================
# 4. RESET REDIS
# ============================================================
echo -e "\n${BLUE}[4/6] Resetting Redis...${NC}"

if container_running "docker-redis-1"; then
    echo "  Flushing all data..."
    docker exec docker-redis-1 redis-cli FLUSHALL 2>/dev/null
    echo -e "  ${GREEN}Redis reset${NC}"
else
    echo -e "  ${YELLOW}Redis not running, skipping${NC}"
fi

# ============================================================
# 5. RESET ELASTICSEARCH (if exists)
# ============================================================
echo -e "\n${BLUE}[5/6] Resetting Elasticsearch...${NC}"

if container_running "docker-elasticsearch-1"; then
    echo "  Deleting all indices..."
    docker exec docker-elasticsearch-1 curl -sX DELETE 'http://localhost:9200/_all' 2>/dev/null || true
    echo -e "  ${GREEN}Elasticsearch reset${NC}"
else
    echo -e "  ${YELLOW}Elasticsearch not running, skipping${NC}"
fi

# ============================================================
# 6. RESTART AND INITIALIZE
# ============================================================
echo -e "\n${BLUE}[6/6] Restarting services...${NC}"

cd "$DOCKER_DIR"

# Start database first
echo "  Starting database..."
docker compose up -d db
sleep 5

# Run migrations
echo "  Running database migrations..."
docker compose up -d api
sleep 10

# Wait for API to be ready
if container_running "docker-api-1"; then
    wait_for_service "docker-api-1" 30

    echo "  Running Alembic migrations..."
    docker exec docker-api-1 alembic upgrade head 2>&1 | tail -5
fi

# Start remaining services
echo "  Starting all services..."
docker compose up -d

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  RESET COMPLETE${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Environment has been reset to clean state."
echo ""
echo "Single Tenant Configuration:"
echo "  - Tenant ID: 00000000-0000-0000-0000-000000000001"
echo "  - Tenant Name: NouxCubeIA Organization"
echo ""
echo "Next steps:"
echo "  1. Wait for services to fully start (~30 seconds)"
echo "  2. Configure your Alfresco connector"
echo "  3. Trigger document sync to index documents"
echo ""
echo "Check service status:"
echo "  docker compose ps"
echo ""
