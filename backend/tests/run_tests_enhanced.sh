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
MAGNIFIER="🔍"
SEPARATOR="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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

info() {
    echo -e "${BLUE}${INFO} $1${NC}"
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

# Función para ejecutar comando con spinner y manejo de errores mejorado
run_with_spinner() {
    local message="$1"
    local command="$2"
    local log_file="$3"
    local initial_errexit_status=$(set +o | grep errexit) # Guardar estado original de errexit
    local initial_xtrace_status=$(set +o | grep xtrace)   # Guardar estado original de xtrace
    
    set +e # Desactivar errexit para esta función
    set +x # Desactivar xtrace (debug) dentro de esta función para evitar spam

    if [ "$DEBUG_MODE" == "true" ]; then
        echo "[DEBUG run_with_spinner] Mensaje: '$message'"
        echo "[DEBUG run_with_spinner] Comando: '$command'"
        echo "[DEBUG run_with_spinner] Archivo de Log: '$log_file'"
    fi
    
    printf "${CYAN}%s${NC} " "$message"
    
    # Ejecutar comando en background
    eval "$command" > "$log_file" 2>&1 &
    pid=$!

    # Verificar si el proceso background se lanzó correctamente
    if ! kill -0 $pid 2>/dev/null; then
        printf "${RED}%s${NC}\n" "$CROSS"
        log "${RED}Fallo crítico al iniciar el comando en background: $command ${NC}"
        log "${RED}Verifica $log_file para más detalles.${NC}"
        if [ -f "$log_file" ] && [ -s "$log_file" ]; then
            cat "$log_file"
        fi
        # Restaurar errexit antes de salir de la función si falla aquí
        if [[ "$initial_errexit_status" == *"errexit"*on* ]]; then
            set -e
        fi
        # Restaurar xtrace si estaba activado
        if [[ "$initial_xtrace_status" == *"xtrace"*on* ]]; then
            set -x
        fi
        return 1
    fi
    
    if [ "$DEBUG_MODE" == "true" ]; then
        echo "[DEBUG run_with_spinner] PID del comando en background: $pid"
    fi
    
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
    
    if [ "$DEBUG_MODE" == "true" ]; then
        echo "[DEBUG run_with_spinner] 'wait \$pid' completado. Código de salida capturado: $exit_code"
    fi
    
    if [ $exit_code -eq 0 ]; then
        printf "${GREEN}%s${NC}\n" "$CHECK"
    else
        printf "${RED}%s${NC}\n" "$CROSS"
    fi
    
    if [ "$DEBUG_MODE" == "true" ]; then
        echo "[DEBUG run_with_spinner] Retornando: $exit_code"
    fi
    
    # Restaurar el estado original de errexit
    if [[ "$initial_errexit_status" == *"errexit"*on* ]]; then
        set -e
    fi
    # Restaurar xtrace si estaba activado
    if [[ "$initial_xtrace_status" == *"xtrace"*on* ]]; then
        set -x
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURACIÓN INICIAL Y PARSEO DE ARGUMENTOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Valores por defecto
MODE="FULL"
DEBUG_MODE="false"
KEEP_CONTAINERS="false"
TIMEOUT_MINUTES=15
LOG_DIR="/tmp"
BUILD_LOG_FILE="$LOG_DIR/build.log"
LOG_FILE="$LOG_DIR/test_output.log"

# Parseo de argumentos mejorado
while [[ $# -gt 0 ]]; do
    case "$1" in
        --simple|-s)
            MODE="SIMPLE"
            shift
            ;;
        --debug|-d)
            DEBUG_MODE="true"
            shift
            ;;
        --keep|-k)
            KEEP_CONTAINERS="true"
            shift
            ;;
        --timeout|-t)
            if [[ "$2" =~ ^[0-9]+$ ]]; then
                TIMEOUT_MINUTES="$2"
                shift 2
            else
                error "El argumento --timeout requiere un número entero"
                exit 1
            fi
            ;;
        --help|-h)
            echo -e "${CYAN}${BOLD}Uso: ./run_tests_enhanced.sh [OPCIONES]${NC}"
            echo -e "Opciones:"
            echo -e "  ${GREEN}--simple, -s${NC}      Ejecutar en modo simple (sin Qdrant)"
            echo -e "  ${GREEN}--debug, -d${NC}       Activar modo debug (más información)"
            echo -e "  ${GREEN}--keep, -k${NC}        Mantener contenedores después de terminar"
            echo -e "  ${GREEN}--timeout, -t NUM${NC} Establecer timeout en minutos (default: 15)"
            echo -e "  ${GREEN}--help, -h${NC}        Mostrar esta ayuda"
            exit 0
            ;;
        *)
            error "Opción desconocida: $1"
            echo "Usa --help para ver las opciones disponibles"
            exit 1
            ;;
    esac
done

# Definición de archivos Docker Compose
COMPOSE_FILE_FULL="../docker/docker-compose.test.yml"
COMPOSE_FILE_SIMPLE="../docker/docker-compose.test.simple.yml"

if [ "$MODE" == "SIMPLE" ]; then
    COMPOSE_FILE=$COMPOSE_FILE_SIMPLE
else
    COMPOSE_FILE=$COMPOSE_FILE_FULL
fi

# Crear directorio de logs si no existe
mkdir -p "$LOG_DIR"

# Limpiar logs anteriores
rm -f "$BUILD_LOG_FILE" "$LOG_FILE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VERIFICACIONES INICIALES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Verificar que estamos en el directorio correcto
if [ ! -f "conftest.py" ]; then
    error "No se encontró conftest.py. Ejecuta desde backend/tests/"
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

# Verificar Docker y Docker Compose
if ! command -v docker &> /dev/null; then
    error "Docker no está instalado o no está en el PATH"
    exit 1
fi

if ! docker info &> /dev/null; then
    error "El servicio Docker no está en ejecución o no tienes permisos suficientes"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    error "Docker Compose no está instalado o no está en el PATH"
    exit 1
fi

# Mostrar header (ahora que MODE y COMPOSE_FILE están definidos)
show_header

# Configurar limpieza al salir o al interrumpir
trap 'cleanup; echo -e "\n ${YELLOW}${WARNING} Tests interrumpidos por el usuario${NC}"; exit 1' INT TERM

# Variables de entorno para tests
export TESTING=true
export COMPOSE_PROJECT_NAME="backend_tests"
start_time=$(date +%s)

# Paso 1: Limpieza
echo -e "\n ${YELLOW}${GEAR} Fase 1: Limpieza de contenedores anteriores ${NC}"
cleanup > /dev/null 2>&1
show_spinner "Limpiando recursos anteriores"

# Paso 2: Construcción
echo -e "\n ${PURPLE}${GEAR} Fase 2: Construcción de imágenes ${NC}"
show_step 2 "Construcción de imágenes Docker" "$GEAR"

# Activar modo debug si está habilitado
if [ "$DEBUG_MODE" == "true" ]; then
    set -x
fi

spinner_message="Construyendo imágenes Docker (usando $COMPOSE_FILE)..."

# Nota: run_with_spinner desactiva temporalmente el modo debug para evitar spam
if run_with_spinner "$spinner_message" "docker compose -f \"$COMPOSE_FILE\" build --no-cache" "$BUILD_LOG_FILE"; then
    success "Construcción de imágenes Docker completada exitosamente."
else
    build_exit_code=$?
    error "Error en la construcción de imágenes (código de salida: $build_exit_code)."
    
    if [ -f "$BUILD_LOG_FILE" ] && [ -s "$BUILD_LOG_FILE" ]; then
        echo -e "\n${RED}${MAGNIFIER} Detalles del error de construcción:${NC}"
        echo -e "${RED}${SEPARATOR}${NC}"
        cat "$BUILD_LOG_FILE"
        echo -e "${RED}${SEPARATOR}${NC}"
    else
        warning "No se encontró el archivo de log $BUILD_LOG_FILE o está vacío."
    fi
    
    exit 1
fi

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
    echo -e "\n${GREEN}${CHECK} ¡Tests completados exitosamente en ${duration}s!${NC}"
    
    # Copiar reportes de cobertura
    if docker volume ls | grep -q "backend_tests_test_coverage"; then
        info "Copiando reporte de cobertura..."
        
        # Crear directorio de destino si no existe
        mkdir -p "$(pwd)/coverage_report"
        
        # Copiar reportes desde el volumen
        docker run --rm \
            -v backend_tests_test_coverage:/source \
            -v "$(pwd)/coverage_report":/dest \
            alpine cp -r /source/. /dest/ 2>/dev/null || true
            
        if [ -f "coverage_report/index.html" ]; then
            success "Reporte de cobertura disponible en $(pwd)/coverage_report/index.html"
        else
            warning "No se pudo copiar el reporte de cobertura"
        fi
    fi
    
    # Mostrar tests más lentos si están disponibles
    if [ -f "$LOG_FILE" ]; then
        if grep -q "slowest durations" "$LOG_FILE"; then
            echo -e "\n${YELLOW}${CLOCK} Tests más lentos:${NC}"
            sed -n '/slowest durations/,/= .* passed/p' "$LOG_FILE" | head -n -1 | tail -n +2 | while IFS= read -r line; do
                echo -e "${YELLOW}  $line${NC}"
            done
        fi
    fi
    
else
    echo -e "\n${RED}${CROSS} Tests fallaron (código de salida: $exit_code)${NC}"
    
    if [ $exit_code -eq 124 ]; then
        echo -e "${YELLOW}${WARNING} Tests terminados por timeout ($TIMEOUT_MINUTES minutos)${NC}"
    fi
    
    # Mostrar errores más relevantes
    if [ -f "$LOG_FILE" ]; then
        # Intentar extraer sección de fallos de pytest
        if grep -q "^=========================== FAILURES ===========================" "$LOG_FILE"; then
            echo -e "\n${RED}${MAGNIFIER} Detalles de los fallos (sección FAILURES de pytest):${NC}"
            show_separator
            sed -n '/^=========================== FAILURES ===========================$/,/^========================= short test summary info =========================/ { /^========================= short test summary info =========================/!p; }' "$LOG_FILE" | while IFS= read -r line; do
                echo -e "${RED}  $line${NC}"
            done
            show_separator
            
            # Mostrar también el resumen corto
            echo -e "\n${RED}${MAGNIFIER} Resumen de fallos:${NC}"
            sed -n '/^========================= short test summary info =========================$/,/^=/ { /^=/!p; }' "$LOG_FILE" | while IFS= read -r line; do
                echo -e "${RED}  $line${NC}"
            done
        else
            # Si no hay sección de FAILURES, mostrar errores genéricos
            echo -e "\n${RED}${MAGNIFIER} Errores encontrados:${NC}"
            show_separator
            grep -i -E "(error|failed|exception|traceback)" "$LOG_FILE" | tail -20 | while IFS= read -r line; do
                echo -e "${RED}  → $line${NC}"
            done
            show_separator
        fi
        
        # Mostrar logs de servicios para debugging
        echo -e "\n${YELLOW}${INFO} Logs de servicios para debugging:${NC}"
        
        echo -e "${YELLOW}--- Base de Datos ---${NC}"
        docker compose -f "$COMPOSE_FILE" logs --tail=10 test-db 2>/dev/null || echo "No se pudieron obtener logs de test-db"
        
        echo -e "${YELLOW}--- Redis ---${NC}"
        docker compose -f "$COMPOSE_FILE" logs --tail=5 test-redis 2>/dev/null || echo "No se pudieron obtener logs de test-redis"
        
        if [ "$MODE" == "FULL" ]; then
            echo -e "${YELLOW}--- Qdrant ---${NC}"
            docker compose -f "$COMPOSE_FILE" logs --tail=5 test-qdrant 2>/dev/null || echo "No se pudieron obtener logs de test-qdrant"
        fi
    fi
fi

# Fase 5: Limpieza final
show_step 5 "Limpieza final" "$GEAR"

if [ "$KEEP_CONTAINERS" == "true" ]; then
    warning "Omitiendo limpieza final (--keep fue especificado)"
    info "Para limpiar manualmente, ejecuta: docker compose -f $COMPOSE_FILE down -v --remove-orphans"
else
    info "Limpiando recursos..."
    cleanup
    
    # Mensaje sobre logs
    if [ -f "$LOG_FILE" ]; then
        info "Los logs de la ejecución están disponibles en: $LOG_FILE"
    fi
    
    # No eliminar logs si estamos en modo debug
    if [ "$DEBUG_MODE" != "true" ]; then
        # Limpiar archivos temporales solo si no estamos en modo debug
        if [ "$exit_code" -eq 0 ]; then
            # Si los tests fueron exitosos, podemos limpiar los logs
            rm -f "$BUILD_LOG_FILE"
        fi
    else
        info "Modo debug activado: conservando archivos de log"
    fi
fi

echo -e "\n${CYAN}${BOLD}Ejecución de tests completada en ${duration}s con código de salida: $exit_code${NC}"

exit $exit_code