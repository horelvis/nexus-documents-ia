#!/bin/bash

# Script avanzado para ejecutar tests con indicadores visuales mejorados
# Versión corregida con mejor manejo de colores y output

set -e

# Colores y símbolos corregidos
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
BOLD='\033[1m'
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
SPINNER="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Función para logging mejorado
log() {
    printf "${BLUE}[%s]${NC} %s\n" "$(date +'%H:%M:%S')" "$1"
}

success() {
    printf "${GREEN}%s %s${NC}\n" "$CHECK" "$1"
}

error() {
    printf "${RED}%s %s${NC}\n" "$CROSS" "$1"
}

warning() {
    printf "${YELLOW}%s %s${NC}\n" "$WARNING" "$1"
}

# Función para mostrar título mejorado
show_header() {
    clear
    printf "${CYAN}${BOLD}\n"
    printf "╭──────────────────────────────────────────────────────────────────────────────╮\n"
    printf "│                          🧪 SUITE DE TESTS BACKEND 🧪                          │\n"
    printf "│                                                                              │\n"
    
    if [[ "$COMPOSE_FILE" == *"simple"* ]]; then
        printf "│  • Modo: SIMPLE (sin Qdrant)                                                │\n"
        printf "│  • Servicios: API, PostgreSQL, Redis                                        │\n"
    else
        printf "│  • Modo: COMPLETO                                                           │\n"
        printf "│  • Servicios: API, PostgreSQL, Redis, Qdrant                               │\n"
    fi
    
    printf "│  • Base de datos: PostgreSQL (temporal)                                     │\n"
    printf "│  • Reportes: Cobertura HTML + Terminal                                      │\n"
    printf "│  • Timeout: 15 minutos máximo                                               │\n"
    printf "│                                                                              │\n"
    printf "│  Uso: ./run_tests_enhanced.sh [--simple|-s]                                 │\n"
    printf "╰──────────────────────────────────────────────────────────────────────────────╯\n"
    printf "${NC}\n"
}

# Función para mostrar progreso visual
show_step() {
    local step_num="$1"
    local step_name="$2"
    local emoji="$3"
    
    printf "\n${BOLD}${CYAN}%s Paso %d: %s${NC}\n" "$emoji" "$step_num" "$step_name"
    printf "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# Función para mostrar spinner mejorado
show_spinner() {
    local message="$1"
    local duration="$2"
    local delay=0.1
    
    printf "${CYAN}%s${NC} " "$message"
    
    for ((i=0; i<duration*10; i++)); do
        local spin_char="${SPINNER:$((i%10)):1}"
        printf "${YELLOW}[%s]${NC}" "$spin_char"
        sleep $delay
        printf "\b\b\b"
    done
    
    printf "${GREEN}%s${NC}\n" "$CHECK"
}

# Función para ejecutar comando con spinner
run_with_spinner() {
    local message="$1"
    local command="$2"
    local log_file="$3"
    
    printf "${CYAN}%s${NC} " "$message"
    
    # Ejecutar comando en background
    eval "$command" > "$log_file" 2>&1 &
    pid=$!
    
    # Mostrar spinner mientras se ejecuta
    i=0
    while kill -0 $pid 2>/dev/null; do
        spin_char="${SPINNER:$((i%10)):1}"
        printf "${YELLOW}[%s]${NC}" "$spin_char"
        sleep 0.1
        printf "\b\b\b"
        ((i++))
    done
    
    # Esperar a que termine y obtener código de salida
    wait $pid
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        printf "${GREEN}%s${NC}\n" "$CHECK"
    else
        printf "${RED}%s${NC}\n" "$CROSS"
    fi
    
    return $exit_code
}

# Función para colorear output de pytest mejorado
colorize_output() {
    while IFS= read -r line; do
        case "$line" in
            *"FAILED"*|*"ERROR"*|*"failed"*|*"error"*)
                printf "${RED}%s %s${NC}\n" "$CROSS" "$line"
                ;;
            *"PASSED"*|*"passed"*|*" ok "*|*"OK"*)
                printf "${GREEN}%s %s${NC}\n" "$CHECK" "$line"
                ;;
            *"WARNING"*|*"warning"*|*"WARN"*)
                printf "${YELLOW}%s %s${NC}\n" "$WARNING" "$line"
                ;;
            *"test_"*|*"::test"*)
                printf "${CYAN}%s %s${NC}\n" "$TEST_TUBE" "$line"
                ;;
            *"Installing"*|*"Collecting"*|*"pip install"*)
                printf "${PURPLE}📦 %s${NC}\n" "$line"
                ;;
            *"coverage"*|*"cov-report"*)
                printf "${GREEN}%s %s${NC}\n" "$CHART" "$line"
                ;;
            *"Health check"*|*"healthy"*|*"ready"*)
                printf "${GREEN}💚 %s${NC}\n" "$line"
                ;;
            *"waiting"*|*"Starting"*|*"Waiting"*)
                printf "${YELLOW}%s %s${NC}\n" "$CLOCK" "$line"
                ;;
            *"="*"="*|*"-"*"-"*)
                printf "${BLUE}%s${NC}\n" "$line"
                ;;
            "")
                echo
                ;;
            *)
                printf "%s\n" "$line"
                ;;
        esac
    done
}

# Función para mostrar estadísticas finales mejorada
show_final_stats() {
    local duration=$1
    local exit_code=$2
    
    printf "\n${WHITE}${BOLD}╭─ ESTADÍSTICAS FINALES ─────────────────────────────────────────────────────╮${NC}\n"
    
    if [ $exit_code -eq 0 ]; then
        printf "${WHITE}│ %s Status: ${GREEN}${BOLD}ÉXITO${NC}\n" "$CHECK"
    else
        printf "${WHITE}│ %s Status: ${RED}${BOLD}FALLO${NC}\n" "$CROSS"
    fi
    
    printf "${WHITE}│ %s Duración: %dm %ds${NC}\n" "$CLOCK" $((duration/60)) $((duration%60))
    printf "${WHITE}│ %s Base de datos: PostgreSQL (temporal)${NC}\n" "$DATABASE"
    printf "${WHITE}│ %s Servicios: API, DB, Redis, Qdrant${NC}\n" "$GEAR"
    
    # Mostrar información de cobertura si existe
    if [ -f "coverage_report/index.html" ]; then
        printf "${WHITE}│ %s Cobertura: coverage_report/index.html${NC}\n" "$CHART"
    fi
    
    printf "${WHITE}│ %s Logs: /tmp/test_output.log${NC}\n" "$INFO"
    printf "${WHITE}╰────────────────────────────────────────────────────────────────────────────╯${NC}\n"
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

# Mostrar header
show_header

# Configurar limpieza
trap 'cleanup; echo -e "\n${YELLOW}${WARNING} Tests interrumpidos por el usuario${NC}"; exit 1' INT TERM

# Variables
export TESTING=true
export COMPOSE_PROJECT_NAME="backend_tests"
start_time=$(date +%s)

# Paso 1: Limpieza
echo -e "\n${YELLOW}${GEAR} Fase 1: Limpieza de contenedores anteriores${NC}"
cleanup > /dev/null 2>&1
show_spinner "Limpiando recursos anteriores"

# Paso 2: Construcción
echo -e "\n${PURPLE}${GEAR} Fase 2: Construcción de imágenes${NC}"
echo -n "${CYAN}Construyendo imágenes Docker${NC} "

# Mostrar progreso de construcción
docker compose -f ../docker/docker-compose.test.yml build --no-cache > /tmp/build.log 2>&1 &
build_pid=$!

# Spinner personalizado para construcción
delay=0.1
spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
while kill -0 $build_pid 2>/dev/null; do
    temp=${spinstr#?}
    printf "${YELLOW}[%c]${NC}" "$spinstr"
    spinstr=$temp${spinstr%"$temp"}
    sleep $delay
    printf "\b\b\b"
done

wait $build_pid
build_exit_code=$?

if [ $build_exit_code -ne 0 ]; then
    printf "${RED}${CROSS}${NC}\n"
    echo -e "${RED}${CROSS} Error en la construcción. Ver /tmp/build.log${NC}"
    exit 1
else
    printf "${GREEN}${CHECK}${NC}\n"
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