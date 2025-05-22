#!/bin/bash

# Script simplificado para ejecutar tests con output mejorado
# Foco en funcionalidad y feedback claro

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

# Símbolos
CHECK="✅"
CROSS="❌"
WARNING="⚠️"
ROCKET="🚀"
GEAR="⚙️"
DATABASE="🗄️"
TEST_TUBE="🧪"
CHART="📊"

# Función para logs con timestamp
log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

# Función para mostrar título
show_header() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                            🧪 BACKEND TEST SUITE 🧪                          ║"
    echo "║                                                                              ║"
    echo "║  • Base de datos: PostgreSQL (temporal)                                     ║"
    echo "║  • Servicios: API, Redis, Qdrant                                            ║"
    echo "║  • Reportes: Cobertura HTML + Terminal                                      ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Función para colorear output de pytest
colorize_output() {
    while IFS= read -r line; do
        case "$line" in
            *"FAILED"*|*"ERROR"*|*"failed"*|*"error"*)
                echo -e "${RED}❌ $line${NC}"
                ;;
            *"PASSED"*|*"passed"*|*" ok "*|*"OK"*)
                echo -e "${GREEN}✅ $line${NC}"
                ;;
            *"WARNING"*|*"warning"*|*"WARN"*)
                echo -e "${YELLOW}⚠️  $line${NC}"
                ;;
            *"test_"*|*"::test"*)
                echo -e "${CYAN}🧪 $line${NC}"
                ;;
            *"Installing"*|*"Collecting"*|*"pip install"*)
                echo -e "${YELLOW}📦 $line${NC}"
                ;;
            *"coverage"*|*"cov-report"*)
                echo -e "${GREEN}📊 $line${NC}"
                ;;
            *"Health check"*|*"healthy"*|*"ready"*)
                echo -e "${GREEN}💚 $line${NC}"
                ;;
            *"waiting"*|*"Starting"*|*"Waiting"*)
                echo -e "${YELLOW}⏳ $line${NC}"
                ;;
            *"="*"="*|*"-"*"-"*)
                echo -e "${BLUE}$line${NC}"
                ;;
            "")
                echo
                ;;
            *)
                echo "$line"
                ;;
        esac
    done
}

# Función de limpieza
cleanup() {
    log "Limpiando recursos..."
    docker compose -f ../docker/docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true
    docker system prune -f --filter "label=test" 2>/dev/null || true
}

# Configurar trap para limpieza
trap 'cleanup; echo -e "\n${YELLOW}⚠️  Tests interrumpidos${NC}"; exit 1' INT TERM

# Verificaciones iniciales
if [ ! -f "conftest.py" ]; then
    error "No se encontró conftest.py. Ejecuta desde backend/tests/"
    exit 1
fi

if [ ! -f "../docker/docker-compose.test.yml" ]; then
    error "No se encontró ../docker/docker-compose.test.yml"
    exit 1
fi

# Mostrar header
show_header

# Variables
export TESTING=true
export COMPOSE_PROJECT_NAME="backend_tests"
start_time=$(date +%s)

# Fase 1: Limpieza
log "${GEAR} Limpiando contenedores anteriores..."
cleanup
success "Limpieza completada"

# Fase 2: Construcción
log "${GEAR} Construyendo imágenes Docker..."
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if docker compose -f ../docker/docker-compose.test.yml build --no-cache; then
    success "Imágenes construidas correctamente"
else
    error "Error al construir imágenes"
    exit 1
fi

# Fase 3: Ejecutar tests
log "${ROCKET} Iniciando tests..."
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Ejecutar tests con timeout y capturar salida
timeout 600s docker compose -f ../docker/docker-compose.test.yml up \
    --abort-on-container-exit --exit-code-from test-api 2>&1 | \
    tee /tmp/test_output.log | colorize_output

exit_code=${PIPESTATUS[0]}
end_time=$(date +%s)
duration=$((end_time - start_time))

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Mostrar resultados
echo -e "\n${WHITE}╔══ RESULTADOS ══════════════════════════════════════════════════════════════╗${NC}"

if [ $exit_code -eq 0 ]; then
    echo -e "${WHITE}║${NC} ${GREEN}✅ STATUS: ÉXITO${NC}"
    echo -e "${WHITE}║${NC} ⏱️  Duración: ${duration}s"
    echo -e "${WHITE}║${NC} ${DATABASE} Base de datos: PostgreSQL (temporal)"
    
    # Copiar reportes de cobertura
    if docker volume ls | grep -q "backend_tests_test_coverage"; then
        echo -e "${WHITE}║${NC} ${CHART} Copiando reporte de cobertura..."
        if docker run --rm \
            -v backend_tests_test_coverage:/source \
            -v $(pwd)/coverage_report:/dest \
            alpine cp -r /source/. /dest/ 2>/dev/null; then
            echo -e "${WHITE}║${NC} ${CHART} Reporte disponible: coverage_report/index.html"
        fi
    fi
    
    success "¡Tests completados exitosamente!"
    
else
    echo -e "${WHITE}║${NC} ${RED}❌ STATUS: FALLO${NC}"
    echo -e "${WHITE}║${NC} ⏱️  Duración: ${duration}s"
    
    if [ $exit_code -eq 124 ]; then
        echo -e "${WHITE}║${NC} ${WARNING} Razón: Timeout (10 minutos)"
    else
        echo -e "${WHITE}║${NC} ${WARNING} Código de salida: $exit_code"
    fi
    
    # Mostrar últimos errores
    if [ -f "/tmp/test_output.log" ]; then
        echo -e "${WHITE}║${NC}"
        echo -e "${WHITE}║${NC} ${RED}🔍 Últimos errores:${NC}"
        grep -i -E "(error|failed|exception)" /tmp/test_output.log | tail -3 | while read line; do
            echo -e "${WHITE}║${NC}   ${RED}→ $line${NC}"
        done
    fi
    
    error "Tests fallaron - revisar logs arriba"
fi

echo -e "${WHITE}╚════════════════════════════════════════════════════════════════════════════╝${NC}"

# Limpieza final
log "Realizando limpieza final..."
cleanup
rm -f /tmp/test_output.log

success "¡Script completado!"
exit $exit_code