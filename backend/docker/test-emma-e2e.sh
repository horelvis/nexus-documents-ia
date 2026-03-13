#!/bin/bash
# =============================================================================
# Test Emma end-to-end as if from the UI (through Main API with KeyCloak auth)
#
# Usage:
#   ./test-emma-e2e.sh "Hola, ¿cómo me llamo?"
#   ./test-emma-e2e.sh "¿Qué documentos tengo?"
#   ./test-emma-e2e.sh                          # defaults to "Hola"
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

# Load only the env vars we need (avoid exporting URLs with special chars)
if [ -f "$ENV_FILE" ]; then
  MICROSERVICES_API_KEY=$(grep '^MICROSERVICES_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
fi

KEYCLOAK_URL="${KEYCLOAK_URL:-https://nouxcubeai.ddns.net:8085}"
REALM="nouxcube"
CLIENT_ID="nouxcube-frontend"
USERNAME="${KC_USERNAME:-horelvis}"
PASSWORD="${KC_PASSWORD:-noux2026}"
API_URL="${API_URL:-https://nouxcubeai.ddns.net:8000}"
QUERY="${1:-Hola}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Emma E2E Test (through Main API + KeyCloak auth)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Query: $QUERY"
echo ""

# Step 1: Get KeyCloak token
echo "[1/3] Getting KeyCloak token for $USERNAME..."
TOKEN_RESPONSE=$(curl -sk -X POST \
  "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=${CLIENT_ID}" \
  -d "username=${USERNAME}" \
  -d "password=${PASSWORD}" 2>/dev/null)

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
if [ -z "$ACCESS_TOKEN" ]; then
  echo "ERROR: Failed to get token"
  echo "$TOKEN_RESPONSE"
  exit 1
fi
echo "  Token OK (${#ACCESS_TOKEN} chars)"

# Step 2: Call Emma stream endpoint (same as frontend)
echo ""
echo "[2/3] Calling ${API_URL}/api/v1/emma/query/stream..."
echo ""

RESPONSE_FILE="/tmp/emma-e2e-response.txt"
curl -sk -N \
  "${API_URL}/api/v1/emma/query/stream" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"${QUERY}\",
    \"session_id\": \"test-e2e-$(date +%s)\",
    \"context\": {
      \"user_id\": \"a060f046-9992-4d1a-87c4-fa5c6f8c066c\"
    }
  }" 2>/dev/null | tee "$RESPONSE_FILE"

echo ""
echo ""
echo "[3/3] Response saved to $RESPONSE_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
