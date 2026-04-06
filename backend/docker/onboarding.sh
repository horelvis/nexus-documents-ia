#!/bin/bash
# =============================================================================
# Onboarding Mode - Maximize indexing throughput for initial tenant setup
# =============================================================================
#
# This script manages the onboarding lifecycle:
#   Phase 1 (INDEX):  vLLM off, Docling on GPU → fast bulk indexing
#   Phase 2 (ENRICH): vLLM on, Docling CPU → generate summaries (optional)
#   Phase 3 (LIVE):   Normal operation → Emma ready
#
# Usage:
#   ./onboarding.sh start           # Enter onboarding mode (GPU → Docling)
#   ./onboarding.sh status          # Check indexing progress
#   ./onboarding.sh sync <conn_id>  # Trigger sync for a connector
#   ./onboarding.sh sync-all        # Trigger sync for ALL connectors
#   ./onboarding.sh finish          # Exit onboarding → normal mode (GPU → vLLM)
#   ./onboarding.sh boe [preset]    # Download BOE legislation (default: all)
# =============================================================================

set -e
cd "$(dirname "$0")"

COMPOSE_BASE="docker-compose.onpremise.yml"
COMPOSE_ONBOARD="docker-compose.onboarding.yml"
DC="docker compose -f $COMPOSE_BASE -f $COMPOSE_ONBOARD"
DC_NORMAL="docker compose -f $COMPOSE_BASE"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Load API key from .env
API_KEY=$(grep MICROSERVICES_API_KEY .env 2>/dev/null | cut -d= -f2)

info()  { echo -e "${GREEN}[ONBOARD]${NC} $1"; }
warn()  { echo -e "${YELLOW}[ONBOARD]${NC} $1"; }
error() { echo -e "${RED}[ONBOARD]${NC} $1"; }
step()  { echo -e "${CYAN}[STEP]${NC} $1"; }

# ─────────────────────────────────────────────────────────────────────────────
# START: Enter onboarding mode
# ─────────────────────────────────────────────────────────────────────────────
cmd_start() {
    info "Entering ONBOARDING MODE..."
    echo ""
    echo "  Configuration:"
    echo "    - vLLM:    OFF (frees ~22GB VRAM)"
    echo "    - Docling: GPU-accelerated (5-10x faster)"
    echo "    - RAG hierarchical summaries: DISABLED"
    echo ""

    step "1/5 Ensuring base services are running..."
    $DC_NORMAL up -d --no-recreate 2>/dev/null || true
    sleep 5

    step "2/5 Stopping vLLM to free GPU (~22GB VRAM)..."
    $DC_NORMAL stop sglang 2>/dev/null || true
    sleep 3

    step "3/5 Stopping Docling CPU (if running)..."
    $DC_NORMAL --profile docling stop docling 2>/dev/null || true

    step "4/5 Starting Docling GPU + applying onboarding config..."
    $DC --profile docling-gpu up -d docling-gpu
    $DC up -d --no-deps weaviate-service

    step "5/5 Waiting for Docling GPU to be healthy..."
    local retries=0
    while [ $retries -lt 30 ]; do
        if docker exec docker-docling-gpu-1 curl -sf http://localhost:5001/health > /dev/null 2>&1; then
            break
        fi
        retries=$((retries + 1))
        sleep 4
        if [ $((retries % 5)) -eq 0 ]; then
            echo "    ... still starting ($((retries * 4))s)"
        fi
    done

    echo ""
    info "ONBOARDING MODE ACTIVE"
    echo ""
    echo "  Next steps:"
    echo "    1. Connect your data sources in the admin UI"
    echo "    2. Run: ./onboarding.sh sync-all"
    echo "    3. Monitor: ./onboarding.sh status"
    echo "    4. When done: ./onboarding.sh finish"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# STATUS: Check indexing progress
# ─────────────────────────────────────────────────────────────────────────────
cmd_status() {
    info "Indexing status across all connectors:"
    echo ""

    docker exec docker-db-1 psql -U nexus_user -d nexus_db -t -A -c "
        SELECT
            c.name as connector,
            c.connector_type as type,
            COUNT(*) FILTER (WHERE d.indexing_status = 'indexed') as indexed,
            COUNT(*) FILTER (WHERE d.indexing_status = 'pending') as pending,
            COUNT(*) FILTER (WHERE d.indexing_status = 'processing') as processing,
            COUNT(*) FILTER (WHERE d.indexing_status = 'failed') as failed,
            COUNT(*) FILTER (WHERE d.indexing_status = 'skipped') as skipped,
            COUNT(*) as total
        FROM indexed_documents d
        JOIN connectors c ON c.id = d.connector_id
        GROUP BY c.name, c.connector_type
        ORDER BY c.name
    " 2>/dev/null | while IFS='|' read -r name type indexed pending processing failed skipped total; do
        echo "  $name ($type):"
        echo "    indexed=$indexed  pending=$pending  processing=$processing  failed=$failed  skipped=$skipped  total=$total"
        if [ "$total" -gt 0 ] 2>/dev/null; then
            pct=$((indexed * 100 / total))
            echo "    progress: ${pct}%"
        fi
        echo ""
    done

    # Check running sync jobs
    echo "  Active sync jobs:"
    docker exec docker-db-1 psql -U nexus_user -d nexus_db -t -A -c "
        SELECT connector_id, status, started_at
        FROM sync_jobs
        WHERE status = 'running'
        ORDER BY started_at DESC
    " 2>/dev/null | while IFS='|' read -r cid status started; do
        echo "    connector=$cid  started=$started"
    done || echo "    (none)"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# SYNC: Trigger indexing for one or all connectors
# ─────────────────────────────────────────────────────────────────────────────
cmd_sync() {
    local connector_id="$1"
    if [ -z "$connector_id" ]; then
        error "Usage: ./onboarding.sh sync <connector_id>"
        echo "  List connectors with: ./onboarding.sh status"
        exit 1
    fi

    # Determine connector type from DB
    local connector_type
    connector_type=$(docker exec docker-db-1 psql -U nexus_user -d nexus_db -t -A -c "
        SELECT connector_type FROM connectors WHERE id = '$connector_id'
    " 2>/dev/null | tr -d '[:space:]')

    if [ -z "$connector_type" ]; then
        error "Connector $connector_id not found"
        exit 1
    fi

    local container=""
    case "$connector_type" in
        google_drive) container="docker-mcp-google-drive-1" ;;
        onedrive)     container="docker-mcp-onedrive-1" ;;
        alfresco)     container="docker-mcp-alfresco-1" ;;
        *)            error "Unknown connector type: $connector_type"; exit 1 ;;
    esac

    info "Triggering sync for $connector_type connector $connector_id..."

    # Step 1: Discover files from remote source → create pending records
    step "  Discovering files..."
    docker exec "$container" curl -s -X POST "http://localhost:8000/sync" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: ${API_KEY}" \
        -d "{\"connector_id\": \"$connector_id\", \"batch_size\": 200}" | python3 -m json.tool 2>/dev/null || true

    sleep 5  # Wait for discovery to complete

    # Step 2: Index all pending documents → download + extract + embed
    step "  Indexing pending documents..."
    docker exec "$container" curl -s -X POST "http://localhost:8000/index-pending" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: ${API_KEY}" \
        -d "{\"connector_id\": \"$connector_id\", \"batch_size\": 200}" | python3 -m json.tool 2>/dev/null || true
    echo ""
}

cmd_sync_all() {
    info "Triggering sync for ALL connectors..."
    echo ""

    docker exec docker-db-1 psql -U nexus_user -d nexus_db -t -A -c "
        SELECT id, connector_type, name FROM connectors WHERE is_active = true ORDER BY name
    " 2>/dev/null | while IFS='|' read -r cid ctype cname; do
        info "  Syncing: $cname ($ctype) → $cid"
        cmd_sync "$cid"
        sleep 2   # stagger to avoid overloading textextract
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# BOE: Download legislation
# ─────────────────────────────────────────────────────────────────────────────
cmd_boe() {
    local preset="$1"

    local ALL_PRESETS="laboral fiscal mercantil civil administrativo compliance propiedad_intelectual comercio_consumidores emprendimiento inmobiliario contabilidad educacion proteccion_datos"

    if [ -n "$preset" ]; then
        info "Downloading BOE preset: $preset"
        curl -s -X POST "http://localhost:8007/boe/download/preset" \
            -H "Content-Type: application/json" \
            -H "X-API-Key: ${API_KEY}" \
            -d "{\"preset\": \"$preset\", \"index_to_weaviate\": true}" | python3 -m json.tool
    else
        info "Downloading ALL BOE presets (13 categories, ~47 laws)..."
        echo ""
        for p in $ALL_PRESETS; do
            step "Downloading: $p"
            curl -s -X POST "http://localhost:8007/boe/download/preset" \
                -H "Content-Type: application/json" \
                -H "X-API-Key: ${API_KEY}" \
                -d "{\"preset\": \"$p\", \"index_to_weaviate\": true}" > /dev/null 2>&1
            echo "  done"
        done
        info "All BOE legislation downloaded and indexed"
    fi
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# FINISH: Exit onboarding mode, return to normal
# ─────────────────────────────────────────────────────────────────────────────
cmd_finish() {
    info "Exiting ONBOARDING MODE..."
    echo ""

    step "1/3 Stopping Docling GPU..."
    $DC --profile docling-gpu stop docling-gpu 2>/dev/null || true
    docker rm -f docker-docling-gpu-1 2>/dev/null || true

    step "2/3 Starting normal stack (SGLang + Docling CPU)..."
    $DC_NORMAL --profile docling up -d

    step "3/3 Waiting for SGLang to load model (~2-3 min)..."
    local retries=0
    while [ $retries -lt 90 ]; do
        if docker exec docker-sglang-1 curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            break
        fi
        retries=$((retries + 1))
        sleep 2
        if [ $((retries % 15)) -eq 0 ]; then
            echo "    ... still loading (${retries}s)"
        fi
    done

    echo ""
    info "NORMAL MODE ACTIVE"
    echo ""
    echo "  - vLLM: Running (Qwen3-14B-AWQ)"
    echo "  - Docling: CPU mode"
    echo "  - Emma: Ready for queries"
    echo ""

    # Show final stats
    cmd_status
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
case "${1:-help}" in
    start)    cmd_start ;;
    status)   cmd_status ;;
    sync)     cmd_sync "$2" ;;
    sync-all) cmd_sync_all ;;
    boe)      cmd_boe "$2" ;;
    finish)   cmd_finish ;;
    *)
        echo "Onboarding Mode - Maximize indexing throughput"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  start           Enter onboarding mode (GPU → Docling, vLLM off)"
        echo "  status          Show indexing progress for all connectors"
        echo "  sync <id>       Trigger sync for one connector"
        echo "  sync-all        Trigger sync for ALL active connectors"
        echo "  boe [preset]    Download BOE legislation (no arg = all 13 presets)"
        echo "  finish          Exit onboarding → normal mode (GPU → vLLM)"
        echo ""
        echo "Typical flow:"
        echo "  1. ./onboarding.sh start"
        echo "  2. ./onboarding.sh boe              # Download legislation"
        echo "  3. ./onboarding.sh sync-all          # Index all connectors"
        echo "  4. ./onboarding.sh status            # Monitor progress"
        echo "  5. ./onboarding.sh finish            # Go live with Emma"
        ;;
esac
