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

# Ejecutar tests
log "🚀 Ejecutando tests..."
start_time=$(date +%s)

# Ejecutar con timeout para evitar que se cuelgue
timeout 600s docker compose -f ../docker/docker-compose.test.yml up --abort-on-container-exit --exit-code-from test-api

# Capturar código de salida
exit_code=$?
end_time=$(date +%s)
duration=$((end_time - start_time))

# Mostrar resultados
if [ $exit_code -eq 0 ]; then
    success "Tests completados exitosamente en ${duration}s"
    
    # Copiar reportes de cobertura si existen
    if docker volume ls | grep -q "backend_tests_test_coverage"; then
        log "📊 Copiando reporte de cobertura..."
        docker run --rm -v backend_tests_test_coverage:/source -v $(pwd)/coverage_report:/dest alpine cp -r /source/. /dest/
        success "Reporte de cobertura disponible en coverage_report/index.html"
    fi
    
else
    if [ $exit_code -eq 124 ]; then
        error "Tests terminados por timeout (10 minutos)"
    else
        error "Tests fallaron con código de salida $exit_code"
    fi
    
    # Mostrar logs de servicios para debugging
    warning "Mostrando logs de servicios para debugging:"
    docker compose -f ../docker/docker-compose.test.yml logs test-db | tail -20
    docker compose -f ../docker/docker-compose.test.yml logs test-redis | tail -10
    docker compose -f ../docker/docker-compose.test.yml logs test-qdrant | tail -10
fi

# La limpieza se hace automáticamente en EXIT trap

exit $exit_code