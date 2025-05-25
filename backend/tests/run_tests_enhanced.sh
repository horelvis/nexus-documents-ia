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

# Función para mostrar título mejorado
show_header() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "╭──────────────────────────────────────────────────────────────────────────────╮"
    echo "│                          🧪 SUITE DE TESTS BACKEND 🧪                          │"
    echo "│                                                                              │"
    
    if [ "$MODE" == "SIMPLE" ]; then
        echo "│  • Modo: SIMPLE (sin Qdrant)                                                │"
        echo "│  • Servicios: API, PostgreSQL, Redis                                        │"
    else # FULL mode
        echo "│  • Modo: COMPLETO                                                           │"
        echo "│  • Servicios: API, PostgreSQL, Redis, Qdrant                               │"
    fi
    
    echo "│  • Archivo Compose: $COMPOSE_FILE                                           │"
    echo "│  • Base de datos: PostgreSQL (temporal)                                     │"
    echo "│  • Reportes: Cobertura HTML + Terminal                                      │"
    echo "│  • Timeout: 15 minutos máximo                                               │"
    echo "│                                                                              │"
    echo "│  Uso: ./run_tests_enhanced.sh [--simple|-s]                                 │"
    echo "╰──────────────────────────────────────────────────────────────────────────────╯"
    echo -e "${NC}"
}

# Función para mostrar progreso visual
show_step() {
    local step_num="$1"
    local step_name="$2"
    local emoji="$3"
    
    printf "\n ${BOLD}${CYAN}%s Paso %d: %s${NC}\n" "$emoji" "$step_num" "$step_name"
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
    local initial_errexit_status=$(set +o | grep errexit) # Guardar estado original de errexit
    set +e # Desactivar errexit para esta función

    echo "[DEBUG run_with_spinner] Mensaje: '$message'"
    echo "[DEBUG run_with_spinner] Comando: '$command'"
    echo "[DEBUG run_with_spinner] Archivo de Log: '$log_file'"
    
    printf "${CYAN}%s${NC} " "$message"
    
    # Ejecutar comando en background
    eval "$command" > "$log_file" 2>&1 &
    pid=$!

    # Verificar si el proceso background se lanzó correctamente
    if ! kill -0 $pid 2>/dev/null; then
        printf "${RED}%s${NC}
" "$CROSS" # Imprimir la X roja
        # Usar 'log' y los colores definidos, no directamente echo con colores aquí
        log "${RED}Fallo crítico al iniciar el comando en background: $command ${NC}"
        log "${RED}Verifica $log_file para más detalles.${NC}"
        if [ -f "$log_file" ] && [ -s "$log_file" ]; then # Verificar también que no esté vacío
            cat "$log_file" # Mostrar el log directamente
        fi
        # Restaurar errexit antes de salir de la función si falla aquí
        if [[ "$initial_errexit_status" == *"errexit"*on* ]]; then
            set -e
        fi
        return 1 # Retornar un código de error inmediatamente
    fi
    echo "[DEBUG run_with_spinner] PID del comando en background: $pid"
    
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
    echo "[DEBUG run_with_spinner] 'wait \$pid' completado. Código de salida capturado: $exit_code"
    
    if [ $exit_code -eq 0 ]; then
        printf "${GREEN}%s${NC}\n" "$CHECK"
    else
        printf "${RED}%s${NC}\n" "$CROSS"
    fi
    
    echo "[DEBUG run_with_spinner] Retornando: $exit_code"
    # Restaurar el estado original de errexit
    if [[ "$initial_errexit_status" == *"errexit"*on* ]]; then
        set -e
    fi
    return $exit_code
}

# Función para colorear output de pytest mejorado
colorize_pytest_output() {
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
    
    printf "\n ${WHITE}${BOLD}╭─ ESTADÍSTICAS FINALES ─────────────────────────────────────────────────────╮${NC}\n"
    
    if [ $exit_code -eq 0 ]; then
        printf "${WHITE}│ %s Status: ${GREEN}${BOLD}ÉXITO${NC}\n" "$CHECK"
    else
        printf "${WHITE}│ %s Status: ${RED}${BOLD}FALLO${NC}\n" "$CROSS"
    fi
    
    printf "${WHITE}│ %s Duración: %dm %ds${NC}\n" "$CLOCK" $((duration/60)) $((duration%60))
    printf "${WHITE}│ %s Base de datos: PostgreSQL (temporal)${NC}\n" "$DATABASE"
    if [ "$MODE" == "SIMPLE" ]; then
        printf "${WHITE}│ %s Servicios: API, DB, Redis${NC}\n" "$GEAR"
    else # FULL mode
        printf "${WHITE}│ %s Servicios: API, DB, Redis, Qdrant${NC}\n" "$GEAR"
    fi
    
    # Mostrar información de cobertura si existe
    if [ -f "coverage_report/index.html" ]; then
        printf "${WHITE}│ %s Cobertura: coverage_report/index.html${NC}\n" "$CHART"
    fi
    
    printf "${WHITE}│ %s Logs: /tmp/test_output.log${NC}\n" "$INFO"
    printf "${WHITE}╰────────────────────────────────────────────────────────────────────────────╯${NC}\n"
}

# Función de limpieza
cleanup() {
    # $COMPOSE_FILE se establece después del parseo de argumentos,
    # pero cleanup puede ser llamado por trap antes.
    # Usaremos el archivo por defecto si COMPOSE_FILE no está seteado aún.
    local current_compose_file=${COMPOSE_FILE:-../docker/docker-compose.test.yml}
    log "Limpiando recursos usando $current_compose_file..."
    docker compose -f "$current_compose_file" down -v --remove-orphans 2>/dev/null || true
    docker system prune -f --filter "label=test" 2>/dev/null || true
}

# Parseo de argumentos para modo Simple/Full
MODE="FULL" # Por defecto, modo completo
if [[ "$1" == "--simple" || "$1" == "-s" ]]; then
    MODE="SIMPLE"
fi

# Definición de archivos Docker Compose
COMPOSE_FILE_FULL="../docker/docker-compose.test.yml"
COMPOSE_FILE_SIMPLE="../docker/docker-compose.test.simple.yml" # Este archivo debe ser creado por el usuario

if [ "$MODE" == "SIMPLE" ]; then
    COMPOSE_FILE=$COMPOSE_FILE_SIMPLE
else
    COMPOSE_FILE=$COMPOSE_FILE_FULL
fi

# Verificaciones iniciales
if [ ! -f "conftest.py" ]; then
    echo -e "${RED}${CROSS} Error: No se encontró conftest.py. Ejecuta desde backend/tests/${NC}"
    exit 1
fi

# Verificar que existe el docker-compose.test.yml apropiado
if [ ! -f "$COMPOSE_FILE" ]; then
    error "No se encontró el archivo Docker Compose: $COMPOSE_FILE"
    if [ "$MODE" == "SIMPLE" ]; then
        warning "Para el modo SIMPLE, necesitas crear $COMPOSE_FILE_SIMPLE."
        warning "Puedes copiar $COMPOSE_FILE_FULL y eliminar el servicio 'test-qdrant' y su 'depends_on' en 'test-api'."
    fi
    exit 1
fi

# Mostrar header (ahora que MODE y COMPOSE_FILE están definidos)
show_header

# Configurar limpieza
trap 'cleanup; echo -e "\n ${YELLOW}${WARNING} Tests interrumpidos por el usuario${NC}"; exit 1' INT TERM

# Variables
export TESTING=true
export COMPOSE_PROJECT_NAME="backend_tests"
start_time=$(date +%s)

# Paso 1: Limpieza
echo -e "\n ${YELLOW}${GEAR} Fase 1: Limpieza de contenedores anteriores ${NC}"
cleanup > /dev/null 2>&1
show_spinner "Limpiando recursos anteriores"

# Paso 2: Construcción
echo -e "\n ${PURPLE}${GEAR} Fase 2: Construcción de imágenes ${NC}"
set -x # Activar Debug de Shell (Temporalmente para esta fase)

spinner_message="Construyendo imágenes Docker (usando $COMPOSE_FILE)..."
build_log_file="/tmp/build.log"

# Limpiar log anterior si existe
rm -f "$build_log_file"

echo "[DEBUG MainScript] Llamando a run_with_spinner para construcción. COMPOSE_FILE=$COMPOSE_FILE"

if run_with_spinner "$spinner_message" "docker compose -f \"$COMPOSE_FILE\" build --no-cache" "$build_log_file"; then
    echo "[DEBUG MainScript] run_with_spinner para construcción retornó éxito."
    success "Construcción de imágenes Docker completada."
else
    build_exit_code_after_spinner=$? 
    echo "[DEBUG MainScript] run_with_spinner para construcción retornó fallo con código: $build_exit_code_after_spinner."
    error "Error en la construcción de imágenes (código de salida: $build_exit_code_after_spinner). Revisa $build_log_file para detalles."
    if [ -f "$build_log_file" ] && [ -s "$build_log_file" ]; then
        echo -e "${RED}" # Iniciar color rojo para el log
        cat "$build_log_file"
        echo -e "${NC}" # Resetear color
    else
        warning "No se encontró el archivo de log $build_log_file o está vacío."
    fi
    exit 1 # Salir del script principal
fi
set +x # Desactivar Debug de Shell

# Paso 3: Ejecución de tests
echo -e "\n ${CYAN}${ROCKET} Fase 3: Ejecutando tests (usando $COMPOSE_FILE)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Ejecutar tests con salida en tiempo real
# El comando de pytest dentro de docker-compose.test.yml ya tiene --durations=10
timeout 900s docker compose -f "$COMPOSE_FILE" up \
    --abort-on-container-exit --exit-code-from test-api 2>&1 | \
    tee /tmp/test_output.log | colorize_pytest_output

exit_code=${PIPESTATUS[0]} # Captura el código de salida de 'docker compose up' (el primer comando en el pipe)
end_time=$(date +%s)
duration=$((end_time - start_time))

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Mostrar estadísticas finales
show_final_stats $duration $exit_code

# Procesar resultados
if [ $exit_code -eq 0 ]; then
    echo -e "\n ${GREEN}${CHECK} ¡Tests completados exitosamente!${NC}"
    
    # Copiar reportes de cobertura
    if docker volume ls | grep -q "backend_tests_test_coverage"; then
        echo -e "${CHART} Copiando reporte de cobertura..."
        docker run --rm \
            -v backend_tests_test_coverage:/source \
            -v $(pwd)/coverage_report:/dest \
            alpine cp -r /source/. /dest/ 2>/dev/null || true
    fi
    
else
    echo -e "\n ${RED}${CROSS} Tests fallaron${NC}"
    
    if [ $exit_code -eq 124 ]; then
        echo -e "${YELLOW}${WARNING} Terminados por timeout (10 minutos)${NC}"
    fi
    
    # Mostrar errores más relevantes
    if [ -f "/tmp/test_output.log" ]; then
        if grep -q "^=========================== FAILURES ===========================" /tmp/test_output.log; then
            echo -e "\n ${RED}🔍 Detalles de los Fallos (pytest FAILURES sección):${NC}"
            sed -n '/^=========================== FAILURES ===========================$/,/^========================= short test summary info =========================/ { /^========================= short test summary info =========================/!p; }' /tmp/test_output.log | while IFS= read -r line; do
                echo -e "${RED}  $line${NC}" # Coloreado simple de todo el bloque
            done
        else
            # Fallback al método anterior si no hay sección de FAILURES detallada
            echo -e "\n ${RED}🔍 Errores encontrados (resumen simple de /tmp/test_output.log):${NC}"
            grep -i -E "(error|failed|exception)" /tmp/test_output.log | tail -15 | while IFS= read -r line; do # Show a bit more for simple summary
                echo -e "${RED}  → $line${NC}"
            done
        fi
    fi
fi

# Limpieza final
echo -e "\n ${YELLOW}${GEAR} Limpieza final...${NC}"
cleanup

# Limpiar archivos temporales
rm -f /tmp/test_output.log /tmp/build.log

exit $exit_code