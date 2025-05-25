#!/bin/bash

# Script de Nueva Generación para Ejecutar Pruebas del Backend
# Ofrece modos simple/completo y una salida clara.

set -e
set -o pipefail

# Variables Globales (se definirán más adelante)
MODE="FULL" # FULL o SIMPLE
# ACTIVE_COMPOSE_FILE se establecerá en parse_arguments_and_set_mode

# Rutas a los archivos Docker Compose
COMPOSE_FILE_BASE="../docker/docker-compose.test.yml"
COMPOSE_FILE_SIMPLE="../docker/docker-compose.test.simple.yml" 
ACTIVE_COMPOSE_FILE="" # Se establecerá dinámicamente

# --- Definiciones de Colores y Emojis (reutilizadas) ---
RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
BLUE='[0;34m'
PURPLE='[0;35m'
CYAN='[0;36m'
WHITE='[1;37m'
BOLD='[1m'
NC='[0m' # No Color

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
CLEAN="🧹"
BUILD_ICON="🏗️" # Icono para construcción

# --- Funciones de Logging ---
log() {
    echo -e "${BLUE}${INFO} [$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}${CHECK} [$(date +'%H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}${CROSS} [$(date +'%H:%M:%S')]${NC} $1"
}

warning() {
    echo -e "${YELLOW}${WARNING} [$(date +'%H:%M:%S')]${NC} $1"
}

# --- Función de Limpieza ---
cleanup() {
    log "${CLEAN} Limpiando recursos de Docker..."
    local compose_to_clean="${ACTIVE_COMPOSE_FILE}"

    if [ -z "$compose_to_clean" ]; then
        # Salvaguarda para traps antes de que ACTIVE_COMPOSE_FILE se defina
        compose_to_clean="$COMPOSE_FILE_BASE" 
        warning "ACTIVE_COMPOSE_FILE no estaba definida en cleanup. Usando default: $compose_to_clean"
    fi

    if [ -f "$compose_to_clean" ]; then
        docker compose -f "$compose_to_clean" down -v --remove-orphans > /dev/null 2>&1 ||             log "${YELLOW}Fallo leve al intentar 'docker compose down'. Puede que no hubiera nada que detener.${NC}"
    else
        # No usar warning() aquí si es un cleanup al final y el archivo simple no existía o si el base no existe.
        log "Archivo compose '$compose_to_clean' no encontrado durante cleanup. Saltando 'down'."
    fi
    
    # Limpieza general de Docker para tests (opcional pero recomendado)
    docker system prune -f --filter "label=test" > /dev/null 2>&1 ||         log "${YELLOW}Fallo leve al intentar 'docker system prune'.${NC}"
    success "${CLEAN} Limpieza de Docker completada."
}

# --- Parseo de Argumentos y Configuración de Modo ---
parse_arguments_and_set_mode() {
    MODE="FULL" # Por defecto
    ACTIVE_COMPOSE_FILE="$COMPOSE_FILE_BASE"

    for arg in "$@"; do
        case $arg in
            -s|--simple)
            MODE="SIMPLE"
            ACTIVE_COMPOSE_FILE="$COMPOSE_FILE_SIMPLE"
            shift # Consumir el argumento
            break # Salir del bucle una vez que se encuentra el modo
            ;;
        esac
    done
    log "Modo de ejecución: $MODE (usando $ACTIVE_COMPOSE_FILE)"
}

# --- Función para Mostrar Encabezado ---
show_header() {
    log "${ROCKET} Iniciando Suite de Pruebas del Backend (NG) ${ROCKET}"
    echo -e "${CYAN}──────────────────────────────────────────────────────────────────────${NC}"
    log "Modo de ejecución: ${BOLD}$MODE${NC}"
    log "Usando archivo Docker Compose: ${BOLD}$ACTIVE_COMPOSE_FILE${NC}"
    if [ "$MODE" == "SIMPLE" ]; then
        log "Servicios esperados: API, PostgreSQL, Redis"
    else # FULL mode
        log "Servicios esperados: API, PostgreSQL, Redis, Qdrant"
    fi
    echo -e "${CYAN}──────────────────────────────────────────────────────────────────────${NC}"
    echo # Línea en blanco para espaciado
}

# --- Función para Colorear Salida de Pytest ---
colorize_pytest_line() {
    local line="$1"
    # Ejemplo simple de coloreado, puede expandirse
    if [[ "$line" == *"::test"* && "$line" == *"PASSED"* ]]; then
        echo -e "${GREEN}${TEST_TUBE} $line${NC}"
    elif [[ "$line" == *"::test"* && "$line" == *"FAILED"* ]]; then
        echo -e "${RED}${TEST_TUBE} $line${NC}"
    elif [[ "$line" == *"ERROR"* || "$line" == *"Traceback"* ]]; then
        echo -e "${RED}$line${NC}"
    elif [[ "$line" == *"WARNING"* ]]; then
        echo -e "${YELLOW}$line${NC}"
    elif [[ "$line" == *"="* && "$line" == *"short test summary info"* ]]; then
        echo -e "${BLUE}${BOLD}$line${NC}"
    elif [[ "$line" == *"collected"* && "$line" == *"items"* ]]; then
        echo -e "${PURPLE}$line${NC}"
    else
        echo "$line" # Sin color para otras líneas
    fi
}

# --- Función para Mostrar Resumen Final ---
show_final_summary() {
    local exit_code=$1
    local duration=$2
    local duration_m=$((duration / 60))
    local duration_s=$((duration % 60))

    echo # Línea en blanco
    log "${CHART} Resumen Final de Pruebas ${CHART}"
    echo -e "${BLUE}----------------------------------------------------------------------${NC}"
    if [ "$exit_code" -eq 0 ]; then
        success "Estado General: ¡Todas las pruebas pasaron!"
    else
        error "Estado General: Fallaron una o más pruebas (código: $exit_code)."
    fi
    log "Modo de Ejecución: $MODE"
    log "Archivo Compose Utilizado: $ACTIVE_COMPOSE_FILE"
    log "${CLOCK} Duración Total: ${duration_m}m ${duration_s}s"
    echo -e "${BLUE}----------------------------------------------------------------------${NC}"
}


# --- Verificaciones Iniciales ---
# Asegurar que se ejecuta desde el directorio correcto
if [ ! -f "conftest.py" ]; then
    # No podemos usar 'error()' aquí si los colores aún no están definidos o si la función no existe.
    # Así que un echo simple es más seguro para estas verificaciones tempranas.
    echo -e "[0;31mError Fatal: No se encontró conftest.py. Este script debe ejecutarse desde el directorio 'backend/tests/'.[0m"
    exit 1
fi

# Asegurar que el archivo docker-compose base existe
BASE_COMPOSE_FILE_FOR_CHECK="../docker/docker-compose.test.yml"
if [ ! -f "$BASE_COMPOSE_FILE_FOR_CHECK" ]; then
    echo -e "[0;31mError Fatal: No se encontró el archivo Docker Compose base: $BASE_COMPOSE_FILE_FOR_CHECK[0m"
    exit 1
fi

log "Verificaciones iniciales completadas."


# --- Función Principal ---
main() {
    start_time=$(date +%s) # Registrar tiempo de inicio del script
    parse_arguments_and_set_mode "$@"

    # Verificar que el archivo Docker Compose activo existe DESPUÉS de parsear argumentos
    if [ ! -f "$ACTIVE_COMPOSE_FILE" ]; then
        error "Archivo Docker Compose no encontrado: $ACTIVE_COMPOSE_FILE"
        if [[ "$MODE" == "SIMPLE" ]]; then
            warning "Asegúrate de haber creado el archivo '$COMPOSE_FILE_SIMPLE' para el modo simple, o ejecuta sin el flag --simple/-s."
        fi
        exit 1
    fi

    show_header # Llamar después de que MODE y ACTIVE_COMPOSE_FILE estén definidos

    # Fase 1: Limpieza Inicial
    log "${CLEAN} Iniciando limpieza inicial de Docker..."
    cleanup # La función cleanup ya tiene sus propios logs de éxito/advertencia
    success "${CLEAN} Limpieza inicial completada."
    echo # Línea en blanco para espaciado

    # Fase 2: Construcción de Imágenes Docker
    log "${BUILD_ICON} Iniciando construcción de imágenes Docker (usando $ACTIVE_COMPOSE_FILE)..."
    # Redirigir stderr a stdout para capturar todo en el log y en la salida de error
    if docker compose -f "$ACTIVE_COMPOSE_FILE" build --no-cache > /tmp/ng_build.log 2>&1; then
        success "${BUILD_ICON} Construcción de imágenes completada."
    else
        build_exit_code=$?
        error "Fallo en la construcción de imágenes (código: $build_exit_code). Ver /tmp/ng_build.log para detalles."
        # Imprimir el log de construcción en caso de error
        if [ -f "/tmp/ng_build.log" ]; then
            echo -e "${RED}--- Inicio: Contenido de /tmp/ng_build.log ---${NC}"
            cat "/tmp/ng_build.log"
            echo -e "${RED}--- Fin: Contenido de /tmp/ng_build.log ---${NC}"
        fi
        exit $build_exit_code
    fi
    echo # Línea en blanco para espaciado

    # Fase 3: Ejecución de Pruebas
    log "${ROCKET} Iniciando ejecución de pruebas con pytest (usando $ACTIVE_COMPOSE_FILE)..."
    
    # Limpiar log de pytest anterior si existe
    PYTEST_LOG_FILE="/tmp/ng_pytest.log"
    rm -f "$PYTEST_LOG_FILE"

    # Asegurar que set -o pipefail esté activo (debería estarlo por el inicio del script)
    # Ejecutar docker compose y procesar su salida
    # La salida completa (stdout y stderr) de docker compose up se redirige a tee.
    # tee escribe a $PYTEST_LOG_FILE y también a stdout.
    # El stdout de tee se pasa al bucle while para colorear.
    # Con set -o pipefail, el código de salida ($?) será el del primer comando que falle en el pipe (docker compose up).
    
    docker compose -f "$ACTIVE_COMPOSE_FILE" up --abort-on-container-exit --exit-code-from test-api 2>&1 | tee "$PYTEST_LOG_FILE" | while IFS= read -r line; do
        colorize_pytest_line "$line"
    done
    pytest_exit_code=${PIPESTATUS[0]} # Capturar el código de salida de 'docker compose up'

    log "Ejecución de pruebas finalizada. Código de salida de pytest: $pytest_exit_code"
    echo # Línea en blanco para espaciado
        
    # Fase 4: Resultados y Reportes
    end_time=$(date +%s)
    duration=$((end_time - start_time))

    show_final_summary "$pytest_exit_code" "$duration"

    if [ "$pytest_exit_code" -ne 0 ]; then
        error "Se detectaron fallos en las pruebas. Mostrando detalles:"
        PYTEST_LOG_FILE="/tmp/ng_pytest.log" # Asegurar que esta variable esté disponible
        if [ -f "$PYTEST_LOG_FILE" ]; then
            # Extraer la sección de FAILURES de pytest
            if grep -q "^=========================== FAILURES ===========================" "$PYTEST_LOG_FILE"; then
                log "Extrayendo detalles de fallos de pytest..."
                sed -n '/^=========================== FAILURES ===========================$/,/^========================= short test summary info =========================/ { /^========================= short test summary info =========================/!p; }' "$PYTEST_LOG_FILE" | while IFS= read -r line; do
                    echo -e "${RED}  $line${NC}"
                done
            else
                warning "No se encontró la sección 'FAILURES' detallada. Mostrando últimas líneas con 'failed' o 'error'."
                grep -E -i "( FAIL |ERROR|FAILED|Traceback)" "$PYTEST_LOG_FILE" | tail -n 30 | while IFS= read -r line; do
                    echo -e "${RED}  $line${NC}"
                done
            fi
        else
            warning "No se encontró el archivo de log de pytest ($PYTEST_LOG_FILE) para mostrar detalles de errores."
        fi
    fi

    # Copiar reporte de cobertura
    COMPOSE_PROJECT_NAME_FOR_VOLUME="backend_tests" 
    COVERAGE_VOLUME_NAME="${COMPOSE_PROJECT_NAME_FOR_VOLUME}_test_coverage"

    if [ "$pytest_exit_code" -eq 0 ] || [ -d "coverage_report_ng" ]; then 
        log "${CHART} Intentando copiar reporte de cobertura..."
        if docker volume inspect "$COVERAGE_VOLUME_NAME" > /dev/null 2>&1; then
            mkdir -p "$(pwd)/coverage_report_ng"
            docker run --rm \
                -v "${COVERAGE_VOLUME_NAME}:/source_volume" \
                -v "$(pwd)/coverage_report_ng:/dest_dir" \
                alpine sh -c "cp -a /source_volume/. /dest_dir/ && echo 'Copia de cobertura completada.' || echo 'Error al copiar cobertura.'"
            
            if [ -f "$(pwd)/coverage_report_ng/index.html" ]; then
                success "Reporte de cobertura copiado a: $(pwd)/coverage_report_ng/index.html"
            else
                warning "Se intentó copiar el reporte de cobertura, pero no se encontró index.html en el destino."
            fi
        else
            warning "Volumen de Docker '$COVERAGE_VOLUME_NAME' para cobertura no encontrado."
        fi
    else
        warning "No se copiará el reporte de cobertura debido a fallos en las pruebas y ausencia de reporte previo."
    fi
    echo # Línea en blanco

    # Fase 5: Limpieza Final
    log "${CLEAN} Iniciando limpieza final de Docker..."
    cleanup # La función cleanup ya tiene sus propios logs
    success "${CLEAN} Limpieza final completada."

    # Limpiar archivos de log temporales
    log "Limpiando archivos de log temporales..."
    rm -f "/tmp/ng_build.log" "$PYTEST_LOG_FILE" # Usar la variable PYTEST_LOG_FILE
    success "Archivos de log temporales eliminados."

    log "Script finalizado. Saliendo con código: $pytest_exit_code"
    exit "$pytest_exit_code"
}

# --- Ejecución del Script ---
# Llamar a la función main pasando todos los argumentos del script
main "$@"
```
