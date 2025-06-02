#!/bin/bash

# Script para ejecutar tests siguiendo buenas prácticas
# Usa base de datos PostgreSQL separada y limpia automáticamente

set -e  # Salir inmediatamente si cualquier comando falla

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# Función de limpieza
cleanup() {
    log "Limpiando recursos..."
    docker compose -f ../docker/docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true
    docker system prune -f --filter "label=test" 2>/dev/null || true
}

# Configurar trap para limpieza al salir
trap cleanup EXIT

# Verificar que estamos en el directorio correcto
if [ ! -f "conftest.py" ]; then
    error "No se encontró conftest.py. Ejecuta desde backend/tests/"
    exit 1
fi

# Verificar que existe el docker-compose.test.yml
if [ ! -f "../docker/docker-compose.test.yml" ]; then
    error "No se encontró ../docker/docker-compose.test.yml"
    exit 1
fi

log "🧪 Iniciando suite de tests con PostgreSQL..."

# Verificar Docker
if ! command -v docker &> /dev/null; then
    error "Docker no está instalado o no está en el PATH"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    error "Docker Compose no está instalado o no está en el PATH"
    exit 1
fi

# Limpiar recursos anteriores
log "🧹 Limpiando contenedores anteriores..."
cleanup

# Variables de entorno para tests
export TESTING=true
export COMPOSE_PROJECT_NAME="backend_tests"

# Construir imágenes si es necesario
log "🔨 Construyendo imágenes para tests..."
docker compose -f ../docker/docker-compose.test.yml build --no-cache

# Verificar que las imágenes se construyeron correctamente
if [ $? -ne 0 ]; then
    error "Error al construir las imágenes"
    exit 1
fi

# Función para mostrar spinner mientras espera
show_spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    echo -n " "
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# Función para mostrar logs en tiempo real con colores
follow_logs() {
    local compose_file=$1
    local service=$2
    
    # Mostrar logs del servicio con colores
    docker compose -f "$compose_file" logs -f "$service" 2>&1 | while IFS= read -r line; do
        case "$line" in
            *"ERROR"*|*"FAILED"*|*"FAIL"*)
                echo -e "${RED}$line${NC}"
                ;;
            *"PASSED"*|*"OK"*|*"SUCCESS"*)
                echo -e "${GREEN}$line${NC}"
                ;;
            *"WARNING"*|*"WARN"*)
                echo -e "${YELLOW}$line${NC}"
                ;;
            *"pytest"*|*"test_"*|*"::test"*)
                echo -e "${BLUE}$line${NC}"
                ;;
            *"Installing"*|*"Collecting"*)
                echo -e "${YELLOW}$line${NC}"
                ;;
            *)
                echo "$line"
                ;;
        esac
    done
}

# Función para mostrar progreso con barra
show_progress() {
    local current=0
    local total=100
    local width=50
    local percentage=0
    
    while [ $current -le $total ]; do
        percentage=$((current))
        filled=$((current * width / total))
        
        printf "\r${BLUE}Progreso: ["
        printf "%*s" $filled | tr ' ' '='
        printf "%*s" $((width - filled)) | tr ' ' '-'
        printf "] %d%% ${NC}" $percentage
        
        sleep 0.5
        current=$((current + 2))
        
        # Salir si el proceso padre ya no existe
        if ! kill -0 $ 2>/dev/null; then
            break
        fi
    done
    echo
}

# Ejecutar tests con mejor feedback visual
log "🚀 Iniciando tests con PostgreSQL..."
start_time=$(date +%s)

# Verificar que los servicios están arrancando
log "📡 Verificando servicios..."

# Iniciar docker compose en background. 
# Esta es la línea clave que inicia los servicios de prueba (DB, Redis, Qdrant) y ejecuta pytest 
# dentro del contenedor 'test-api'. La salida de pytest se redirige a /tmp/test_output.log.
docker compose -f ../docker/docker-compose.test.yml up --abort-on-container-exit --exit-code-from test-api > /tmp/test_output.log 2>&1 &
compose_pid=$!

# Mostrar progreso mientras arranca
echo -n "${YELLOW}⏳ Esperando servicios"
for i in {1..10}; do
    echo -n "."
    sleep 1
    # Verificar si ya terminó
    if ! kill -0 $compose_pid 2>/dev/null; then
        break
    fi
done
echo -e " listo!${NC}"

# Mostrar logs en tiempo real
log "📋 Mostrando progreso de tests en tiempo real:"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Seguir logs del contenedor de tests
timeout 600s docker compose -f ../docker/docker-compose.test.yml logs -f test-api 2>&1 | while IFS= read -r line; do
    case "$line" in
        *"FAILED"*|*"ERROR"*|*"failed"*)
            echo -e "${RED}❌ $line${NC}"
            ;;
        *"PASSED"*|*"passed"*|*" ok "*)
            echo -e "${GREEN}✅ $line${NC}"
            ;;
        *"WARNING"*|*"warning"*)
            echo -e "${YELLOW}⚠️  $line${NC}"
            ;;
        *"test_"*|*"::test"*|*"pytest"*)
            echo -e "${BLUE}🧪 $line${NC}"
            ;;
        *"Installing"*|*"Collecting"*|*"pip install"*)
            echo -e "${YELLOW}📦 $line${NC}"
            ;;
        *"Esperando"*|*"waiting"*|*"ready"*)
            echo -e "${BLUE}⏳ $line${NC}"
            ;;
        *"coverage"*|*"cov"*)
            echo -e "${GREEN}📊 $line${NC}"
            ;;
        *"="*)
            # Líneas con iguales suelen ser separadores de pytest
            echo -e "${BLUE}$line${NC}"
            ;;
        "")
            # Línea vacía, no mostrar nada
            ;;
        *)
            echo "$line"
            ;;
    esac
done &

# Esperar a que termine el proceso
wait $compose_pid

# Capturar código de salida
exit_code=$?
end_time=$(date +%s)
duration=$((end_time - start_time))

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Mostrar resultados con estadísticas
if [ $exit_code -eq 0 ]; then
    success "Tests completados exitosamente en ${duration}s"
    
    # Mostrar resumen si está disponible
    # El archivo /tmp/test_output.log contiene la salida completa de pytest,
    # incluyendo el informe de las pruebas más lentas (--durations=10).
    # Aquí se muestra un breve resumen de los resultados generales.
    if [ -f "/tmp/test_output.log" ]; then
        echo -e "\n${BLUE}📈 Resumen de tests (últimas líneas de /tmp/test_output.log):${NC}"
        grep -E "(passed|failed|error|warning|slowest reported)" /tmp/test_output.log | tail -n 20 | while read line; do # Show more lines to potentially include duration summary
            case "$line" in
                *"failed"*|*"error"*)
                    echo -e "${RED}  $line${NC}"
                    ;;
                *"passed"*)
                    echo -e "${GREEN}  $line${NC}"
                    ;;
                *"slowest reported"*) # Highlight slowest test summary
                    echo -e "${YELLOW}  $line${NC}"
                    ;;
                *)
                    echo -e "${BLUE}  $line${NC}"
                    ;;
            esac
        done
    fi
    
    # Copiar reportes de cobertura si existen
    if docker volume ls | grep -q "backend_tests_test_coverage"; then
        log "📊 Copiando reporte de cobertura..."
        # El script se ejecuta desde backend/tests/, por lo que $(pwd) es /app/backend/tests
        # El reporte se copia a /app/backend/tests/coverage_report/
        docker run --rm -v backend_tests_test_coverage:/source -v "$(pwd)/coverage_report":/dest alpine cp -r /source/. /dest/ 2>/dev/null || true
        if [ -f "coverage_report/index.html" ]; then # This path is relative to where the script is run
            success "Reporte de cobertura disponible en $(pwd)/coverage_report/index.html"
        fi
    fi
    
else
    if [ $exit_code -eq 124 ]; then
        error "Tests terminados por timeout (10 minutos)"
    else
        error "Tests fallaron con código de salida $exit_code"
    fi
    
    # Mostrar logs de servicios para debugging
    warning "Últimos logs de servicios para debugging:"
    echo -e "${YELLOW}--- Base de Datos ---${NC}"
    docker compose -f ../docker/docker-compose.test.yml logs --tail=10 test-db 2>/dev/null || echo "No se pudieron obtener logs de test-db"
    
    echo -e "${YELLOW}--- Redis ---${NC}"
    docker compose -f ../docker/docker-compose.test.yml logs --tail=5 test-redis 2>/dev/null || echo "No se pudieron obtener logs de test-redis"
    
    echo -e "${YELLOW}--- Qdrant ---${NC}"
    docker compose -f ../docker/docker-compose.test.yml logs --tail=5 test-qdrant 2>/dev/null || echo "No se pudieron obtener logs de test-qdrant"
    
    # Mostrar últimos errores del log principal
    if [ -f "/tmp/test_output.log" ]; then
        echo -e "\n${RED}🔍 Últimos errores encontrados:${NC}"
        grep -i -E "(error|failed|exception)" /tmp/test_output.log | tail -10 | while read line; do
            echo -e "${RED}  $line${NC}"
        done
    fi
fi

# Limpiar archivo temporal
rm -f /tmp/test_output.log

# La limpieza se hace automáticamente en EXIT trap

exit $exit_code