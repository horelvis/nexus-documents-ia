#!/bin/bash

# 🚀 Script de Ejecución Rápida de Pruebas - NouxCubeIA
# =======================================================

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Función para imprimir con colores
print_header() {
    echo -e "${BLUE}🚀 NouxCubeIA - Suite de Pruebas de Integración${NC}"
    echo -e "${BLUE}==================================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

print_step() {
    echo -e "${PURPLE}🔸 $1${NC}"
}

# Función de ayuda
show_help() {
    echo "Uso: $0 [OPCIONES]"
    echo ""
    echo "🚀 Suite de Pruebas de Integración - NouxCubeIA"
    echo "⚠️  TODOS los tests se ejecutan dentro de contenedores Docker"
    echo ""
    echo "Opciones disponibles:"
    echo "  --help, -h          Mostrar esta ayuda"
    echo "  --quick, -q         Tests rápidos dentro de contenedores"
    echo "  --full, -f          Tests completos con Docker (recomendado)"
    echo "  --unit, -u          Solo tests unitarios en contenedor"
    echo "  --integration, -i   Solo tests de integración en contenedor"
    echo "  --validation, -v    Solo validación del sistema en contenedor"
    echo "  --performance, -p   Tests de performance en contenedor"
    echo "  --coverage, -c      Generar reporte de cobertura"
    echo "  --clean             Limpiar contenedores y datos de test"
    echo "  --setup             Configurar entorno de testing"
    echo ""
    echo "Ejemplos:"
    echo "  $0 --quick              # Tests rápidos en contenedor"
    echo "  $0 --full               # Tests completos (recomendado)"
    echo "  $0 --unit --coverage    # Tests unitarios con cobertura"
    echo "  $0 --clean              # Limpiar contenedores"
    echo "  $0 --setup              # Configurar entorno"
    echo ""
    echo "📋 Notas importantes:"
    echo "  • Todos los tests se ejecutan dentro de contenedores Docker"
    echo "  • Los reportes se generan en backend/coverage_report/"
    echo "  • Los contenedores se limpian automáticamente"
}

# Función para verificar prerrequisitos
check_prerequisites() {
    print_step "Verificando prerrequisitos..."

    # Verificar Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker no está instalado"
        exit 1
    fi

    # Verificar Docker Compose
    if ! command -v docker &> /dev/null && docker compose version &> /dev/null; then
        print_error "Docker Compose no está disponible"
        exit 1
    fi

    # Verificar Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 no está instalado"
        exit 1
    fi

    # Verificar Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js no está instalado"
        exit 1
    fi

    print_success "Prerrequisitos verificados"
}

# Función para limpiar entorno
clean_environment() {
    print_step "Limpiando entorno de testing..."

    # Detener contenedores
    cd backend/docker
    docker compose down -v --remove-orphans 2>/dev/null || true

    # Limpiar imágenes no utilizadas
    docker system prune -f --filter "label=test" 2>/dev/null || true

    # Limpiar archivos temporales
    rm -rf backend/tests/__pycache__ 2>/dev/null || true
    rm -rf backend/htmlcov 2>/dev/null || true
    rm -rf backend/.coverage 2>/dev/null || true
    rm -rf backend/coverage.xml 2>/dev/null || true
    rm -f /tmp/test_output.log 2>/dev/null || true

    print_success "Entorno limpiado"
}

# Función para configurar entorno
setup_environment() {
    print_step "Configurando entorno de testing..."

    # Instalar dependencias de Python
    print_info "Instalando dependencias de Python..."
    cd backend
    pip install -r requirements.txt
    pip install pytest pytest-cov pytest-asyncio requests psutil

    # Instalar dependencias de Node.js
    print_info "Instalando dependencias de Node.js..."
    cd ../frontend
    npm ci

    # Verificar configuración
    print_info "Verificando configuración..."
    if [ ! -f "../backend/.env.test" ]; then
        print_warning "Creando archivo de configuración de test..."
        cat > ../backend/.env.test << EOF
ENVIRONMENT=test
DEBUG=true
SECRET_KEY=test-secret-key-for-testing-only
DATABASE_URL=postgresql://test_user:test_password@localhost:5432/test_db
ASYNC_DATABASE_URL=postgresql+asyncpg://test_user:test_password@localhost:5432/test_db
REDIS_URL=redis://localhost:6379/1
CLERK_SECRET_KEY=test-clerk-secret-key
CLERK_PUBLISHABLE_KEY=test-clerk-publishable-key
WEAVIATE_URL=http://localhost:8080
ELASTICSEARCH_URL=http://localhost:9200
USE_MOCK_STORAGE=true
TESTING=true
EOF
    fi

    print_success "Entorno configurado"
}

# Función para ejecutar tests de validación
run_validation_tests() {
    print_step "Ejecutando tests de validación del sistema..."

    # Ejecutar validación dentro del contenedor
    cd backend/docker
    if docker compose -f docker-compose.test.yml run --rm test-api python3 /app/validate_system.py; then
        print_success "Validación del sistema completada"
        cd ../..
        return 0
    else
        print_error "Validación del sistema fallida"
        cd ../..
        return 1
    fi
}

# Función para ejecutar tests unitarios
run_unit_tests() {
    print_step "Ejecutando tests unitarios dentro de contenedores..."

    cd backend/docker

    # Ejecutar tests dentro del contenedor
    if [ "$COVERAGE" = true ]; then
        docker compose -f docker-compose.test.yml run --rm test-api pytest tests -v --cov=app --cov-report=term --cov-report=html:/app/coverage_report --cov-fail-under=70
    else
        docker compose -f docker-compose.test.yml run --rm test-api pytest tests -v
    fi

    local result=$?
    if [ $result -eq 0 ]; then
        print_success "Tests unitarios completados"
        if [ "$COVERAGE" = true ]; then
            print_info "Reporte de cobertura disponible en: backend/coverage_report/index.html"
        fi
    else
        print_error "Tests unitarios fallaron"
    fi

    cd ../..
    return $result
}

# Función para ejecutar tests de integración
run_integration_tests() {
    print_step "Ejecutando tests de integración dentro de contenedores..."

    cd backend/docker

    # Ejecutar tests de integración dentro del contenedor
    if docker compose -f docker-compose.test.yml run --rm test-api python3 tests/test_validation_complete.py; then
        print_success "Tests de integración completados"
        cd ../..
        return 0
    else
        print_error "Tests de integración fallaron"
        cd ../..
        return 1
    fi
}

# Función para ejecutar tests de performance
run_performance_tests() {
    print_step "Ejecutando tests de performance..."

    cd backend

    # Tests básicos de performance
    python3 -c "
import time
import requests

def test_response_time(url, num_requests=10):
    print(f'Testing {url}...')
    times = []
    for i in range(num_requests):
        start = time.time()
        try:
            response = requests.get(url, timeout=5)
            end = time.time()
            if response.status_code == 200:
                times.append(end - start)
        except:
            pass

    if times:
        avg_time = sum(times) / len(times)
        print(f'Average response time: {avg_time:.3f}s')
        return avg_time < 1.0
    return False

# Test health endpoint
if test_response_time('http://localhost:8000/api/v1/health', 5):
    print('✅ Performance test passed')
else:
    print('❌ Performance test failed')
    exit(1)
"

    print_success "Tests de performance completados"
}

# Función para ejecutar tests completos con Docker
run_full_tests() {
    print_step "Ejecutando tests completos dentro de contenedores..."

    cd backend/docker

    # Ejecutar suite completa de tests
    if docker compose -f docker-compose.test.yml up --abort-on-container-exit; then
        print_success "Tests completos ejecutados exitosamente"
        print_info "Reportes disponibles en: backend/coverage_report/"
        cd ../..
        return 0
    else
        print_error "Tests completos fallaron"
        cd ../..
        return 1
    fi
}

# Función para ejecutar tests rápidos
run_quick_tests() {
    print_step "Ejecutando tests rápidos dentro de contenedores..."

    cd backend/docker

    # Ejecutar tests básicos dentro del contenedor
    if docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_api/test_auth.py -v; then
        print_success "Tests rápidos completados"
        cd ../..
        return 0
    else
        print_error "Tests rápidos fallaron"
        cd ../..
        return 1
    fi
}

# Variables de control
QUICK=false
FULL=false
UNIT=false
INTEGRATION=false
VALIDATION=false
PERFORMANCE=false
COVERAGE=false
CLEAN=false
SETUP=false

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --quick|-q)
            QUICK=true
            shift
            ;;
        --full|-f)
            FULL=true
            shift
            ;;
        --unit|-u)
            UNIT=true
            shift
            ;;
        --integration|-i)
            INTEGRATION=true
            shift
            ;;
        --validation|-v)
            VALIDATION=true
            shift
            ;;
        --performance|-p)
            PERFORMANCE=true
            shift
            ;;
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --setup)
            SETUP=true
            shift
            ;;
        *)
            print_error "Opción desconocida: $1"
            show_help
            exit 1
            ;;
    esac
done

# Función principal
main() {
    print_header

    # Ejecutar acciones especiales primero
    if [ "$CLEAN" = true ]; then
        clean_environment
        exit 0
    fi

    if [ "$SETUP" = true ]; then
        check_prerequisites
        setup_environment
        exit 0
    fi

    # Verificar prerrequisitos
    check_prerequisites

    # Determinar qué tests ejecutar
    if [ "$QUICK" = true ]; then
        run_quick_tests
    elif [ "$FULL" = true ]; then
        run_full_tests
    elif [ "$UNIT" = true ]; then
        run_unit_tests
    elif [ "$INTEGRATION" = true ]; then
        run_integration_tests
    elif [ "$VALIDATION" = true ]; then
        run_validation_tests
    elif [ "$PERFORMANCE" = true ]; then
        run_performance_tests
    else
        # Por defecto, ejecutar tests rápidos
        print_info "No se especificó tipo de test. Ejecutando tests rápidos..."
        run_quick_tests
    fi
}

# Ejecutar función principal
main "$@"