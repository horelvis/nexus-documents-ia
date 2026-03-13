#!/bin/bash
#
# Sanity Check — Verify Emma platform is fully operational
#
# Usage:
#   ./sanity-check.sh              # All tiers (infra + integration + e2e)
#   ./sanity-check.sh infra        # Tier 1 only (fast, ~1s)
#   ./sanity-check.sh integration  # Tier 2 only (~2s)
#   ./sanity-check.sh e2e          # Tier 3 only (~2s)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load API key from .env
API_KEY=$(grep MICROSERVICES_API_KEY .env 2>/dev/null | cut -d= -f2 || echo "")
BASE_URL="https://localhost:8009"

TIER="${1:-all}"

echo "=========================================="
echo "  Emma Platform Sanity Check"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# Check if emma-agent-service is running
if ! docker compose ps emma-agent-service 2>/dev/null | grep -q "Up"; then
    echo "CRITICAL: emma-agent-service is not running"
    echo "  Run: cd backend/docker && ./start-dev.sh"
    exit 1
fi

run_check() {
    local endpoint="$1"
    local label="$2"
    local timeout="${3:-30}"

    echo -n "  $label ... "

    local response
    response=$(curl -sk --max-time "$timeout" \
        -H "X-API-Key: $API_KEY" \
        "$BASE_URL/diagnostics/$endpoint" 2>/dev/null)

    if [ $? -ne 0 ] || [ -z "$response" ]; then
        echo "FAIL (no response)"
        return 1
    fi

    local status
    status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
    local total_ms
    total_ms=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_ms','?'))" 2>/dev/null)

    if [ "$status" = "healthy" ]; then
        echo "OK (${total_ms}ms)"
    elif [ "$status" = "degraded" ]; then
        echo "WARN (${total_ms}ms)"
        # Show failed checks
        echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for name, check in d.get('checks', {}).items():
    if check.get('status') != 'ok':
        print(f'    -> {name}: {check.get(\"status\")} — {check.get(\"error\", check.get(\"reason\", \"\"))}')
" 2>/dev/null
    else
        echo "FAIL ($status, ${total_ms}ms)"
        echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for name, check in d.get('checks', {}).items():
    if check.get('status') != 'ok':
        print(f'    -> {name}: {check.get(\"error\", check.get(\"reason\", \"\"))}')
" 2>/dev/null
        return 1
    fi
    return 0
}

run_full() {
    echo -n "  Full diagnostics ... "

    local response
    response=$(curl -sk --max-time 90 \
        -X POST \
        -H "X-API-Key: $API_KEY" \
        "$BASE_URL/diagnostics/run" 2>/dev/null)

    if [ $? -ne 0 ] || [ -z "$response" ]; then
        echo "FAIL (no response)"
        return 1
    fi

    local status
    status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
    local total_ms
    total_ms=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_ms','?'))" 2>/dev/null)

    echo ""
    echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for tier_name, tier in d.get('tiers', {}).items():
    checks = tier.get('checks', {})
    ok = sum(1 for c in checks.values() if c.get('status') == 'ok')
    total = len(checks)
    tier_ms = tier.get('total_ms', 0)
    tier_status = tier.get('status', '?')
    icon = 'OK' if tier_status == 'healthy' else ('WARN' if tier_status == 'degraded' else 'FAIL')
    print(f'    [{icon}] {tier_name}: {ok}/{total} checks ({tier_ms:.0f}ms)')
    for name, check in checks.items():
        s = check.get('status', '?')
        ms = check.get('latency_ms', 0)
        detail = check.get('detail', check.get('error', check.get('reason', '')))
        icon2 = '+' if s == 'ok' else ('-' if s == 'skipped' else 'X')
        print(f'      {icon2} {name}: {detail} ({ms:.0f}ms)')
" 2>/dev/null

    echo ""
    if [ "$status" = "healthy" ]; then
        echo "  RESULT: ALL OK (${total_ms}ms)"
        echo ""
        return 0
    elif [ "$status" = "degraded" ]; then
        echo "  RESULT: DEGRADED — some non-critical checks failed (${total_ms}ms)"
        echo ""
        return 0
    else
        echo "  RESULT: CRITICAL — platform has failures (${total_ms}ms)"
        echo ""
        return 1
    fi
}

case "$TIER" in
    infra)
        run_check "infra" "Infrastructure (Tier 1)" 10
        ;;
    integration)
        run_check "integration" "Integration (Tier 2)" 30
        ;;
    e2e)
        run_check "e2e" "E2E Pipeline (Tier 3)" 60
        ;;
    all|"")
        run_full
        ;;
    *)
        echo "Usage: $0 [infra|integration|e2e|all]"
        exit 1
        ;;
esac
