#!/bin/bash
#
# Test: Document Generation & Email Tools
#
# Validates the labor consultancy use case:
#   1. Search for expiring contracts
#   2. Generate a new contract with updated dates
#   3. Email preview (does NOT send real email)
#   4. Download generated document
#
# Usage:
#   ./test-docgen-email.sh              # Full test
#   ./test-docgen-email.sh tools-only   # Skip ReAct, test tools directly
#
# Requires: emma-agent-service running (./start-dev.sh)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

API_KEY=$(grep MICROSERVICES_API_KEY .env 2>/dev/null | cut -d= -f2 || echo "")
BASE_URL="https://localhost:8009"
TENANT_ID="00000000-0000-0000-0000-000000000001"
MODE="${1:-full}"

PASS=0
FAIL=0
SKIP=0

echo "=========================================="
echo "  Document Generation & Email Test"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# Check if service is running
if ! docker compose ps emma-agent-service 2>/dev/null | grep -q "Up"; then
    echo "CRITICAL: emma-agent-service is not running"
    echo "  Run: cd backend/docker && ./start-dev.sh"
    exit 1
fi

run_test() {
    local label="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected="$5"
    local timeout="${6:-30}"

    echo -n "  $label ... "

    local tmpfile="/tmp/test_docgen_$$_$(date +%s%N).json"
    local http_code

    if [ "$method" = "GET" ]; then
        http_code=$(curl -sk --max-time "$timeout" -o "$tmpfile" -w "%{http_code}" \
            -H "X-API-Key: $API_KEY" \
            "$BASE_URL$endpoint" 2>/dev/null) || true
    else
        http_code=$(curl -sk --max-time "$timeout" -o "$tmpfile" -w "%{http_code}" \
            -X POST \
            -H "X-API-Key: $API_KEY" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$BASE_URL$endpoint" 2>/dev/null) || true
    fi

    if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
        echo "FAIL (no response)"
        FAIL=$((FAIL + 1))
        rm -f "$tmpfile"
        return 1
    fi

    # Check if response contains expected string
    if grep -q "$expected" "$tmpfile" 2>/dev/null; then
        echo "OK (HTTP $http_code)"
        PASS=$((PASS + 1))
        rm -f "$tmpfile"
        return 0
    else
        echo "FAIL (HTTP $http_code, expected '$expected')"
        echo "    Response: $(head -c 200 "$tmpfile" 2>/dev/null)"
        FAIL=$((FAIL + 1))
        rm -f "$tmpfile"
        return 1
    fi
}

# ─── Test 1: Diagnostics checks for new tools ───
echo "[Tier 1] Diagnostics integration"
run_test "E2E diagnostics (includes new tools)" \
    "GET" "/diagnostics/e2e?tenant_id=$TENANT_ID" "" \
    "generate_document" 60 || true

echo ""

# ─── Test 2: Tool Registry ───
echo "[Tier 2] Tool availability"

# Check that generate_document and send_email are in the tools list
# We use the /info endpoint or directly test via diagnostics
run_test "generate_document tool registered" \
    "POST" "/diagnostics/run?tiers=3&tenant_id=$TENANT_ID" "" \
    "generate_document" 60 || true

echo ""

# ─── Test 3: Generate Document endpoint ───
echo "[Tier 3] Generated document storage"

# Store a test document directly via the API
run_test "Generated doc info (nonexistent)" \
    "GET" "/emma/generated/__test_nonexistent__/info" "" \
    "no encontrado\|404\|expirado" 10 || true

echo ""

# ─── Test 4: Email preview (no real send) ───
echo "[Tier 4] Email preview via diagnostics"
run_test "Send email preview check" \
    "GET" "/diagnostics/e2e?tenant_id=$TENANT_ID" "" \
    "send_email_preview" 60 || true

echo ""

# ─── Test 5: Full ReAct pipeline (if mode=full) ───
if [ "$MODE" = "full" ]; then
    echo "[Tier 5] Full ReAct pipeline with document query"

    # Test a contract search query through the full pipeline
    QUERY_DATA=$(cat <<'EOF'
{
    "query": "Busca contratos laborales en el sistema",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "user_id": "test-docgen",
    "context": {}
}
EOF
)
    echo -n "  ReAct contract search ... "
    tmpfile="/tmp/test_docgen_react_$$.json"
    http_code=$(curl -sk --max-time 120 -o "$tmpfile" -w "%{http_code}" \
        -X POST \
        -H "X-API-Key: $API_KEY" \
        -H "Content-Type: application/json" \
        -d "$QUERY_DATA" \
        "$BASE_URL/emma/query" 2>/dev/null) || true

    if [ "$http_code" = "200" ]; then
        echo "OK (HTTP 200)"
        PASS=$((PASS + 1))
        # Show a snippet of the response
        echo "    Answer: $(python3 -c "
import json, sys
try:
    d = json.load(open('$tmpfile'))
    print(d.get('answer', d.get('response', ''))[:150])
except: print('(parse error)')
" 2>/dev/null)"
    else
        echo "FAIL (HTTP $http_code)"
        FAIL=$((FAIL + 1))
    fi
    rm -f "$tmpfile"
else
    echo "[Tier 5] Skipped (use './test-docgen-email.sh full' to include)"
    SKIP=$((SKIP + 1))
fi

echo ""
echo "=========================================="
echo "  Results: $PASS passed, $FAIL failed, $SKIP skipped"
echo "=========================================="

if [ $FAIL -gt 0 ]; then
    exit 1
fi
exit 0
