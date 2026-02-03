#!/bin/bash
# =============================================================================
# Test Suite: Emma Social Channel API
# =============================================================================
# Prueba las respuestas de Emma simulando mensajes de Slack/Telegram
#
# Ejecutar: bash tests/test_channel_api.sh
#
# Variables de entorno opcionales:
#   API_BASE  - URL base de la API (default: http://localhost:8009)
#   API_KEY   - API key para autenticación
#   TENANT_ID - ID del tenant de prueba
# =============================================================================

API_BASE="${API_BASE:-http://localhost:8009}"
TENANT_ID="${TENANT_ID:-00000000-0000-0000-0000-000000000001}"
API_KEY="${API_KEY:-}"

# Build auth header if API_KEY is provided
AUTH_HEADER=""
if [ -n "$API_KEY" ]; then
    AUTH_HEADER="-H \"X-API-Key: $API_KEY\""
fi

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "  TEST: Emma Social Channel Responses"
echo "======================================================================"
echo ""

# Function to test a query
test_query() {
    local name="$1"
    local query="$2"
    local category="$3"

    echo -e "${YELLOW}[$category]${NC} $name"
    echo "   Query: \"$query\""

    # Build curl command with optional API key
    if [ -n "$API_KEY" ]; then
        response=$(curl -s -X POST "$API_BASE/emma/query" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -H "X-API-Key: $API_KEY" \
            -d "{
                \"query\": \"$query\",
                \"tenant_id\": \"$TENANT_ID\",
                \"context\": {
                    \"channel_type\": \"slack\",
                    \"response_style\": \"conversational\",
                    \"social_channel_mode\": true,
                    \"location\": {
                        \"city\": \"Molina de Segura\",
                        \"region\": \"Murcia\",
                        \"country\": \"España\",
                        \"timezone\": \"Europe/Madrid\"
                    }
                }
            }")
    else
        response=$(curl -s -X POST "$API_BASE/emma/query" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $TENANT_ID" \
            -d "{
                \"query\": \"$query\",
                \"tenant_id\": \"$TENANT_ID\",
                \"context\": {
                    \"channel_type\": \"slack\",
                    \"response_style\": \"conversational\",
                    \"social_channel_mode\": true,
                    \"location\": {
                        \"city\": \"Molina de Segura\",
                        \"region\": \"Murcia\",
                        \"country\": \"España\",
                        \"timezone\": \"Europe/Madrid\"
                    }
                }
            }")
    fi

    # Extract answer
    answer=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('answer','ERROR')[:200])" 2>/dev/null)

    if [ -z "$answer" ] || [ "$answer" == "ERROR" ]; then
        echo -e "   ${RED}❌ Error en respuesta${NC}"
        echo "   Raw: $(echo $response | head -c 100)"
    else
        echo -e "   ${GREEN}✅ Respuesta:${NC}"
        echo "   $answer"
    fi
    echo ""
}

echo "=== PREGUNTAS LEGALES/LABORALES ==="
echo ""
test_query "Jornada laboral" "¿cuál es la jornada máxima laboral en España?" "legal"
test_query "Estatuto Trabajadores" "¿qué dice el artículo 34 del Estatuto de los Trabajadores?" "legal"
test_query "RGPD" "¿cuáles son las principales obligaciones del RGPD?" "legal"
test_query "Vacaciones" "¿cuántos días de vacaciones me corresponden por ley?" "legal"

echo "=== PREGUNTAS SOBRE DOCUMENTOS ==="
echo ""
test_query "Buscar contratos" "busca los contratos de 2024" "documents"
test_query "Contar documentos" "¿cuántos documentos tengo?" "documents"
test_query "Facturas" "¿hay alguna factura de enero?" "documents"

echo "=== SALUDOS Y AYUDA ==="
echo ""
test_query "Saludo" "hola, ¿en qué puedes ayudarme?" "greeting"
test_query "Capacidades" "¿qué puedes hacer?" "capabilities"

echo "=== BÚSQUEDA WEB (Ubicación/Clima) ==="
echo ""
test_query "Clima" "¿qué tiempo hace hoy?" "web_search"
test_query "Clima específico" "uff, qué mal tiempo, ¿cómo está el clima en Madrid?" "web_search"
test_query "Noticias" "¿cuáles son las últimas noticias?" "web_search"

echo "======================================================================"
echo "  Tests completados"
echo "======================================================================"
