#!/bin/bash

# Script avanzado para ejecutar tests con indicadores visuales mejorados
# Incluye barras de progreso, spinners y salida en tiempo real con colores

set -e

# Colores y símbolos
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

# Símbolos Unicode
CHECK="✅"
CROSS="❌"
WARNING="⚠️"
INFO="ℹ️"
ROCKET="🚀"
GEAR="⚙️"
DATABASE="🗄️"
TEST_TUBE="🧪"
CHART="📊"
CLOCK="⏱️"

# Función para mostrar título con borde
show_title() {
    local title="$1"
    local width=80
    local padding=$(( (width - ${#title} - 2) / 2 ))
    
    echo -e "${BLUE}╭$(printf '─%.0s' $(seq 1 $((width-2))))╮${NC}"
    printf "${BLUE}│%*s%s%*s│${NC}\n" $padding "" "$title" $padding ""
    echo -e "${BLUE}╰$(printf '─%.0s' $(seq 1 $((width-2))))╯${NC}"
}

# Función para mostrar spinner animado
show_spinner() {
    local pid=$1
    local message=$2
    local delay=0.1
    local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    
    echo -n "${CYAN}${message}${NC} "
    while kill -0 $pid 2>/dev/null; do
        local temp=${spinstr#?}
        printf "${YELLOW}[%c]${NC}" "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b"
    done
    printf "${GREEN}${CHECK}${NC}\n"
}

# Función para mostrar barra de progreso
show_progress_bar() {
    local progress=$1
    local total=$2
    local width=50
    local percentage=$((progress * 100 / total))
    local filled=$((progress * width / total))
    local empty=$((width - filled))
    
    printf "\r${WHITE}Progress: ${BLUE}["
    printf "%*s" $filled | tr ' ' '█'
    printf "%*s" $empty | tr ' ' '░'
    printf "] %d%%${NC}" $percentage
}

# Función para parsear y colorear logs de pytest
colorize_pytest_output() {
    while IFS= read -r line; do
        case "$line" in
            *"FAILED"*|*"ERROR"*|*"failed"*|*"error"*)
                echo -e "${RED}${CROSS} $line${NC}"
                ;;
            *"PASSED"*|*"passed"*|*" ok "*|*"OK"*)
                echo -e "${GREEN}${CHECK} $line${NC}"
                ;;
            *"WARNING"*|*"warning"*|*"WARN"*)
                echo -e "${YELLOW}${WARNING} $line${NC}"
                ;;
            *"test_"*|*"::test"*|*"pytest"*|*"collecting"*)
                echo -e "${CYAN}${TEST_TUBE} $line${NC}"
                ;;
            *"Installing"*|*"Collecting"*|*"pip install"*)
                echo -e "${PURPLE}📦 $line${NC}"
                ;;
            *"coverage"*|*"cov-report"*)
                echo -e "${GREEN}${CHART} $line${NC}"
                ;;
            *"Health check"*|*"healthy"*|*"ready"*)
                echo -e "${GREEN}💚 $line${NC}"
                ;;
            *"Waiting"*|*"waiting"*|*"Starting"*)
                echo -e "${YELLOW}${CLOCK} $line${NC}"
                ;;
            *"="*"="*)
                # Separadores de pytest
                echo -e "${BLUE}$line${NC}"
                ;;
            *"short test summary"*|*"FAILURES"*|*"ERRORS"*)
                echo -e "${WHITE}${line}${NC}"
                ;;
            "")
                # Línea vacía
                echo
                ;;
            *)
                echo "$line"
                ;;
        esac
    done
}

# Función para mostrar estadísticas finales
show_final_stats() {
    local duration=$1
    local exit_code=$2
    
    echo -e "\n${WHITE}╭─ Estadísticas Finales $(printf '─%.0s' $(seq 1 50))╮${NC}"
    echo -e "${WHITE}│${NC}"
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${WHITE}│ ${GREEN}${CHECK} Status: ÉXITO${NC}"
    else
        echo -e "${WHITE}│ ${RED}${CROSS} Status: FALLO${NC}"
    fi
    
    echo -e "${WHITE}│ ${CLOCK} Duración: ${duration}s${NC}"
    echo -e "${WHITE}│ ${DATABASE} Base de datos: PostgreSQL (temporal)${NC}"
    echo -e "${WHITE}│ ${GEAR} Servicios: API, DB, Redis, Qdrant${NC}"
    
    # Mostrar información de cobertura si existe
    if [ -f "coverage_report/index.html" ]; then
        echo -e "${WHITE}│ ${CHART} Cobertura: coverage_report/index.html${NC}"
    fi
    
    echo -e "${WHITE}│${NC}"
    echo -e "${WHITE}╰$(printf '─%.0s' $(seq 1 70))╯${NC}"
}

# Función de limpieza
cleanup() {
    docker compose -f ../docker/docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true
    docker system prune -f --filter "label=test" 2>/dev/null || true
}

# Verificaciones iniciales
if [ ! -f "conftest.py" ]; then
    echo -e "${RED}${CROSS} Error: No se encontró conftest.py. Ejecuta desde backend/tests/${NC}"
    exit 1
fi

if [ ! -f "../docker/docker-compose.test.yml" ]; then
    echo -e "${RED}${CROSS} Error: No se encontró ../docker/docker-compose.test.yml${NC}"
    exit 1
fi

# Mostrar título
clear
show_title "🧪 SUITE DE TESTS BACKEND 🧪"

# Configurar limpieza
trap 'cleanup; echo -e "\n${YELLOW}${WARNING} Tests interrumpidos por el usuario${NC}"; exit 1' INT TERM

# Variables
export TESTING=true
export COMPOSE_PROJECT_NAME="backend_tests"
start_time=$(date +%s)

# Paso 1: Limpieza
echo -e "\n${YELLOW}${GEAR} Fase 1: Limpieza de contenedores anteriores${NC}"
cleanup &
show_spinner $! "Limpiando recursos anteriores"

# Paso 2: Construcción
echo -e "\n${PURPLE}${GEAR} Fase 2: Construcción de imágenes${NC}"
docker compose -f ../docker/docker-compose.test.yml build --no-cache > /tmp/build.log 2>&1 &
show_spinner $! "Construyendo imágenes Docker"

if [ $? -ne 0 ]; then
    echo -e "${RED}${CROSS} Error en la construcción. Ver /tmp/build.log${NC}"
    exit 1
fi

# Paso 3: Ejecución de tests
echo -e "\n${CYAN}${ROCKET} Fase 3: Ejecutando tests${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Ejecutar tests con salida en tiempo real
timeout 600s docker compose -f ../docker/docker-compose.test.yml up \
    --abort-on-container-exit --exit-code-from test-api 2>&1 | \
    tee /tmp/test_output.log | colorize_pytest_output

exit_code=${PIPESTATUS[0]}
end_time=$(date +%s)
duration=$((end_time - start_time))

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Mostrar estadísticas finales
show_final_stats $duration $exit_code

# Procesar resultados
if [ $exit_code -eq 0 ]; then
    echo -e "\n${GREEN}${CHECK} ¡Tests completados exitosamente!${NC}"
    
    # Copiar reportes de cobertura
    if docker volume ls | grep -q "backend_tests_test_coverage"; then
        echo -e "${CHART} Copiando reporte de cobertura..."
        docker run --rm \
            -v backend_tests_test_coverage:/source \
            -v $(pwd)/coverage_report:/dest \
            alpine cp -r /source/. /dest/ 2>/dev/null || true
    fi
    
else
    echo -e "\n${RED}${CROSS} Tests fallaron${NC}"
    
    if [ $exit_code -eq 124 ]; then
        echo -e "${YELLOW}${WARNING} Terminados por timeout (10 minutos)${NC}"
    fi
    
    # Mostrar errores más relevantes
    if [ -f "/tmp/test_output.log" ]; then
        echo -e "\n${RED}🔍 Errores encontrados:${NC}"
        grep -i -E "(error|failed|exception)" /tmp/test_output.log | tail -5 | while read line; do
            echo -e "${RED}  → $line${NC}"
        done
    fi
fi

# Limpieza final
echo -e "\n${YELLOW}${GEAR} Limpieza final...${NC}"
cleanup

# Limpiar archivos temporales
rm -f /tmp/test_output.log /tmp/build.log

exit $exit_code