#!/usr/bin/env bash
set -euo pipefail

# Smoke test for the Weaviate+Elysia pipeline.
# Requires MICROSERVICES_API_KEY in the environment.

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${MICROSERVICES_API_KEY:-}"
TENANT_ID="${TENANT_ID:-default}"
CAG_USER_ID="${CAG_USER_ID:-cli-smoke-test}"
CAG_CONVERSATION_ID="${CAG_CONVERSATION_ID:-smoke-run-$(date +%s)}"
SEARCH_QUERY="${SEARCH_QUERY:-contratos de servicios cloud}"
CAG_QUERY="${CAG_QUERY:-Resume los riesgos principales del Master Service Agreement con Acme}"

if [[ -z "${API_KEY}" ]]; then
  echo "❌ MICROSERVICES_API_KEY environment variable is required."
  exit 1
fi

log_step() {
  printf "\n[%s] %s\n" "$(date '+%H:%M:%S')" "$1"
}

invoke_api() {
  local label="$1"
  local url="$2"
  local payload="$3"
  local include_tenant_header="${4:-true}"
  local tmp_response
  tmp_response="$(mktemp)"

  log_step "Calling ${label}..."
  local curl_cmd=(
    curl -sS
    -w "\nHTTP_STATUS:%{http_code}\n"
    -H "Content-Type: application/json"
    -H "X-API-Key: ${API_KEY}"
    -X POST "${url}"
    -d "${payload}"
  )
  if [[ "${include_tenant_header}" == "true" ]]; then
    curl_cmd+=(-H "X-Tenant-ID: ${TENANT_ID}")
  fi

  local raw
  raw="$("${curl_cmd[@]}" >"${tmp_response}")" || {
    rm -f "${tmp_response}"
    echo "❌ Request to ${label} failed."
    exit 1
  }

  local status
  status="$(printf "%s" "${raw}" | awk -FHTTP_STATUS: 'NF>1 {print $2}' | tail -n1)"

  if [[ "${status}" != "200" ]]; then
    echo "❌ ${label} failed with status ${status}"
    cat "${tmp_response}"
    rm -f "${tmp_response}"
    exit 1
  fi

  echo "✅ ${label} succeeded (HTTP ${status})"

  if command -v jq >/dev/null 2>&1; then
    jq 'del(.documents?[]?.content)' "${tmp_response}" 2>/dev/null || cat "${tmp_response}"
  else
    cat "${tmp_response}"
  fi

  rm -f "${tmp_response}"
}

search_payload=$(cat <<JSON
{
  "query": "${SEARCH_QUERY}",
  "limit": 5,
  "filters": {}
}
JSON
)

cag_payload=$(cat <<JSON
{
  "query": "${CAG_QUERY}",
  "tenant_id": "${TENANT_ID}",
  "user_id": "${CAG_USER_ID}",
  "context": {
    "conversation_id": "${CAG_CONVERSATION_ID}"
  }
}
JSON
)

invoke_api "Document Search" "${BASE_URL}/api/v1/documents/search" "${search_payload}" "true"
invoke_api "Elysia Agent" "${BASE_URL}/api/v1/cag/query" "${cag_payload}" "false"

log_step "Smoke test completed."
