# 🧪 Guía de Pruebas de Integración - NexusDocs360

## 📋 Resumen

Esta guía documenta el sistema completo de pruebas de integración para NexusDocs360, incluyendo ejecución local, CI/CD con GitHub Actions, y mejores prácticas para desarrollo y testing.

## 🎯 Tipos de Pruebas

### 1. **Pruebas Unitarias** (`pytest tests/test_*.py`)
- Tests individuales de funciones y métodos
- Ejecutan rápido, sin dependencias externas
- Cobertura de código alta

### 2. **Pruebas de Integración** (`test_validation_complete.py`)
- Tests de integración entre servicios
- Validación de APIs y bases de datos
- Tests end-to-end con datos reales

### 3. **Pruebas de Servicios** (`test_validation_simple.py`)
- Validación de servicios individuales
- Health checks y conectividad
- Tests de infraestructura

### 4. **Pruebas de Validación del Sistema** (`validate_system.py`)
- Validación completa del sistema
- Checks de todos los servicios
- Reporte de estado general

## 🚀 Ejecución Local

### ⚠️ **IMPORTANTE: Tests Dentro de Contenedores**

**TODOS los tests deben ejecutarse dentro de contenedores Docker** para garantizar consistencia, aislamiento y reproducibilidad. Los tests ejecutados fuera de contenedores pueden fallar debido a diferencias en el entorno.

### Prerrequisitos

```bash
# Instalar Docker y Docker Compose
sudo apt-get update
sudo apt-get install docker.io docker-compose

# Verificar instalación
docker --version
docker compose version

# Añadir usuario al grupo docker (opcional, evita usar sudo)
sudo usermod -aG docker $USER
# Reiniciar sesión o ejecutar: newgrp docker
```

### Opción 1: Tests Completos con Docker (RECOMENDADO)

```bash
# 1. Ejecutar tests completos dentro de contenedores
cd backend/docker
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# 2. Ver reportes de cobertura (generados automáticamente)
cd ../..
open backend/coverage_report/index.html

# 3. Ejecutar validación adicional del sistema (opcional)
python3 validate_system.py
```

**Ventajas de esta opción:**
- ✅ Tests ejecutados dentro de contenedores
- ✅ Servicios aislados para testing
- ✅ Reportes de cobertura automáticos
- ✅ Limpieza automática de recursos
- ✅ Entorno consistente y reproducible

### Opción 2: Tests Rápidos con Contenedores

```bash
# 1. Ejecutar tests rápidos dentro de contenedores
cd backend/docker
docker compose -f docker-compose.test.yml up test-api --abort-on-container-exit

# 2. Ver resultados en tiempo real
# Los logs se muestran en la terminal
```

### Opción 3: Tests Personalizados Dentro de Contenedores

```bash
# Ejecutar tests específicos dentro del contenedor
cd backend/docker

# Tests unitarios
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_api/ -v

# Tests de integración
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_validation_complete.py -v

# Tests con cobertura
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/ -v --cov=app --cov-report=term

# Ejecutar un test específico
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_api/test_auth.py::test_login -v
```

### Opción 4: Tests Individuales por Servicio (Dentro de Contenedores)

```bash
cd backend/docker

# Tests de autenticación
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_api/test_auth.py -v

# Tests de documentos
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_api/test_documents.py -v

# Tests de servicios
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_services/ -v

# Tests con debug interactivo
docker compose -f docker-compose.test.yml run --rm test-api bash
# Dentro del contenedor: pytest tests/test_api/test_auth.py -v -s --pdb
```

## 🔧 Configuración de Entorno

### Variables de Entorno para Testing

```bash
# Archivo: backend/.env.test
ENVIRONMENT=test
DEBUG=true
SECRET_KEY=test-secret-key-for-testing-only

# Base de datos de test
DATABASE_URL=postgresql://test_user:test_password@localhost:5432/test_db
ASYNC_DATABASE_URL=postgresql+asyncpg://test_user:test_password@localhost:5432/test_db

# Redis de test
REDIS_URL=redis://localhost:6379/1

# Clerk (test mode)
CLERK_SECRET_KEY=test-clerk-secret-key
CLERK_PUBLISHABLE_KEY=test-clerk-publishable-key

# Servicios externos
WEAVIATE_URL=http://localhost:8080
ELASTICSEARCH_URL=http://localhost:9200

# Storage (mock para tests)
USE_MOCK_STORAGE=true
TESTING=true
```

## 🐳 **Ejecución de Tests Dentro de Contenedores**

### **¿Por qué ejecutar tests dentro de contenedores?**

✅ **Consistencia**: Entorno idéntico en desarrollo, CI/CD y producción
✅ **Aislamiento**: Tests no afectan el sistema host ni otros tests
✅ **Reproducibilidad**: Resultados consistentes en cualquier máquina
✅ **Limpieza automática**: Recursos liberados automáticamente
✅ **Dependencias controladas**: Versiones exactas de todas las dependencias
✅ **Paralelización**: Múltiples suites de tests sin conflictos

### **Arquitectura de Testing con Docker**

```
┌─────────────────┐    ┌─────────────────┐
│   test-api      │    │   Servicios     │
│   (pytest)      │◄──►│   PostgreSQL    │
│                 │    │   Redis         │
│   Contenedor    │    │   Qdrant        │
│   Principal     │    │   LangChain     │
└─────────────────┘    │   Storage       │
                       └─────────────────┘
```

### **Configuración del Contenedor de Tests**

```yaml
# backend/docker/docker-compose.test.yml - Servicio test-api
test-api:
  build:
    context: ..
    dockerfile: docker/Dockerfile
  environment:
    # Variables específicas para testing
    - TESTING=true
    - POSTGRES_SERVER=test-db
    - REDIS_HOST=test-redis
    - QDRANT_HOST=test-qdrant
    # ... más variables
  depends_on:
    test-db:
      condition: service_healthy
    test-redis:
      condition: service_healthy
    # ... otros servicios
  volumes:
    # Montar código fuente para desarrollo
    - ../tests:/app/tests:ro
    - ../app:/app/app:ro
    - ../credentials:/app/credentials:ro
    - test_coverage:/app/coverage_report
  command: >
    bash -c "
    pip install pytest pytest-cov &&
    sleep 10 &&
    pytest tests -v --cov=app --cov-report=html:/app/coverage_report
    "
```

### **Comandos Esenciales para Tests en Contenedores**

```bash
# Ejecutar suite completa
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# Ejecutar tests específicos
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_api/test_auth.py -v

# Debug interactivo
docker compose -f docker-compose.test.yml run --rm test-api bash

# Ver logs en tiempo real
docker compose -f docker-compose.test.yml up test-api

# Limpiar después de tests
docker compose -f docker-compose.test.yml down -v
```

## 📊 Reportes de Cobertura

### Generar Reportes de Cobertura

```bash
# Reporte HTML detallado
cd backend
python3 -m pytest tests/ --cov=app --cov-report=html --cov-report=term

# Reporte XML para CI/CD
python3 -m pytest tests/ --cov=app --cov-report=xml --cov-report=term

# Reporte con líneas faltantes
python3 -m pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
```

### Ver Reportes

```bash
# Abrir reporte HTML
open backend/htmlcov/index.html

# Ver resumen en terminal
python3 -m pytest tests/ --cov=app --cov-report=term
```

## 🔄 CI/CD con GitHub Actions

### Workflows Disponibles

#### 1. **PR Validation** (`.github/workflows/pr-validation.yml`)
- ✅ Linting (Frontend & Backend)
- ✅ Tests unitarios
- ✅ Build check
- ✅ Security scan
- ✅ Cobertura de código

#### 2. **Integration Tests** (Nuevo - ver abajo)
- ✅ Tests de integración completos
- ✅ Validación de servicios
- ✅ Tests end-to-end
- ✅ Reportes detallados

#### 3. **Nightly Tests** (Nuevo - ver abajo)
- ✅ Tests completos con datos reales
- ✅ Performance testing
- ✅ Load testing básico

### Configuración de GitHub Actions

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
  schedule:
    # Ejecutar diariamente a las 2 AM UTC
    - cron: '0 2 * * *'
  workflow_dispatch:

env:
  NODE_VERSION: '18'
  PYTHON_VERSION: '3.9'
  DOCKER_COMPOSE_VERSION: '2.0.1'

jobs:
  integration-test:
    name: Integration Test Suite
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      weaviate:
        image: semitechnologies/weaviate:latest
        ports:
          - 8080:8080
        env:
          QUERY_DEFAULTS_LIMIT: 25
          AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'

      elasticsearch:
        image: elasticsearch:8.11.0
        env:
          discovery.type: single-node
          xpack.security.enabled: 'false'
          "ES_JAVA_OPTS": "-Xms512m -Xmx512m"
        ports:
          - 9200:9200
          - 9300:9300

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}

    - name: Setup Node.js
      uses: actions/setup-node@v4
      with:
        node-version: ${{ env.NODE_VERSION }}
        cache: 'npm'
        cache-dependency-path: frontend/package-lock.json

    - name: Setup Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Install system dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y postgresql-client redis-tools curl

    - name: Install Python dependencies
      working-directory: ./backend
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov pytest-asyncio requests psutil

    - name: Install Node.js dependencies
      working-directory: ./frontend
      run: npm ci

    - name: Wait for services to be ready
      run: |
        echo "⏳ Waiting for PostgreSQL..."
        for i in {1..30}; do
          if pg_isready -h localhost -p 5432 -U test_user; then
            echo "✅ PostgreSQL is ready"
            break
          fi
          sleep 2
        done

        echo "⏳ Waiting for Redis..."
        for i in {1..30}; do
          if redis-cli -h localhost -p 6379 ping | grep -q PONG; then
            echo "✅ Redis is ready"
            break
          fi
          sleep 2
        done

        echo "⏳ Waiting for Weaviate..."
        for i in {1..30}; do
          if curl -s http://localhost:8080/v1/meta > /dev/null; then
            echo "✅ Weaviate is ready"
            break
          fi
          sleep 2
        done

        echo "⏳ Waiting for Elasticsearch..."
        for i in {1..30}; do
          if curl -s http://localhost:9200/_cluster/health > /dev/null; then
            echo "✅ Elasticsearch is ready"
            break
          fi
          sleep 2
        done

    - name: Run system validation
      run: python3 validate_system.py

    - name: Run integration tests
      working-directory: ./backend/tests
      env:
        DATABASE_URL: postgresql://test_user:test_password@localhost:5432/test_db
        REDIS_URL: redis://localhost:6379
        ENVIRONMENT: test
        SECRET_KEY: test-secret-key
        CLERK_SECRET_KEY: test-clerk-secret
        WEAVIATE_URL: http://localhost:8080
        ELASTICSEARCH_URL: http://localhost:9200
      run: |
        python3 test_validation_complete.py

    - name: Run unit tests with coverage
      working-directory: ./backend
      env:
        DATABASE_URL: postgresql://test_user:test_password@localhost:5432/test_db
        REDIS_URL: redis://localhost:6379
        ENVIRONMENT: test
        SECRET_KEY: test-secret-key
        CLERK_SECRET_KEY: test-clerk-secret
      run: |
        python3 -m pytest tests/ -v --cov=app --cov-report=xml --cov-report=term --cov-report=html

    - name: Run frontend tests
      working-directory: ./frontend
      run: npm test -- --coverage --watchAll=false

    - name: Upload coverage reports
      uses: codecov/codecov-action@v3
      with:
        file: ./backend/coverage.xml
        flags: backend
        name: Backend Coverage

    - name: Upload coverage reports (Frontend)
      uses: codecov/codecov-action@v3
      with:
        file: ./frontend/coverage/lcov.info
        flags: frontend
        name: Frontend Coverage

    - name: Upload test artifacts
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: test-results-${{ github.run_number }}
        path: |
          backend/htmlcov/
          backend/test-results/
          frontend/coverage/

  performance-test:
    name: Performance Tests
    runs-on: ubuntu-latest
    needs: integration-test
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}

    - name: Install dependencies
      working-directory: ./backend
      run: |
        pip install -r requirements.txt
        pip install locust pytest

    - name: Run performance tests
      working-directory: ./backend
      run: |
        # Aquí irían los tests de performance con Locust
        echo "🚀 Performance tests would run here"
        # locust -f tests/performance_tests.py --headless --users 10 --spawn-rate 1 --run-time 30s

  security-test:
    name: Security Tests
    runs-on: ubuntu-latest
    needs: integration-test

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}

    - name: Install security tools
      run: |
        pip install bandit safety
        npm install -g audit-ci

    - name: Run Python security scan
      working-directory: ./backend
      run: |
        bandit -r app/ -f json -o security-report.json || true
        safety check -r requirements.txt --json > safety-report.json || true

    - name: Run Node.js security audit
      working-directory: ./frontend
      run: audit-ci --config audit-ci.json || true

    - name: Upload security reports
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: security-reports-${{ github.run_number }}
        path: |
          backend/security-report.json
          backend/safety-report.json
```

## 📈 Métricas y Reportes

### Cobertura de Código

```bash
# Ver cobertura actual
cd backend
python3 -m pytest tests/ --cov=app --cov-report=term

# Cobertura por archivo
python3 -m pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

### Reportes de Performance

```bash
# Tests de carga básicos
cd backend/tests
python3 -c "
import time
import requests

def test_response_time():
    start = time.time()
    response = requests.get('http://localhost:8000/api/v1/health')
    end = time.time()

    response_time = end - start
    print(f'Response time: {response_time:.3f}s')
    assert response_time < 1.0, f'Response too slow: {response_time}s'
    assert response.status_code == 200

test_response_time()
"
```

## 🔧 Debugging y Troubleshooting

### Problemas Comunes con Tests en Contenedores

#### 1. **Tests fallan por servicios no disponibles**
```bash
# Verificar servicios de test
cd backend/docker
docker compose -f docker-compose.test.yml ps

# Ver logs de servicios específicos
docker compose -f docker-compose.test.yml logs test-db
docker compose -f docker-compose.test.yml logs test-redis

# Reiniciar servicios de test
docker compose -f docker-compose.test.yml down
docker compose -f docker-compose.test.yml up -d

# Verificar conectividad desde el contenedor
docker compose -f docker-compose.test.yml run --rm test-api python3 validate_system.py
```

#### 2. **Contenedores no se inician correctamente**
```bash
# Ver logs detallados
cd backend/docker
docker compose -f docker-compose.test.yml up

# Debug de healthchecks
docker compose -f docker-compose.test.yml run --rm test-db pg_isready -U test_user -d test_db
docker compose -f docker-compose.test.yml run --rm test-redis redis-cli ping

# Forzar reconstrucción
docker compose -f docker-compose.test.yml build --no-cache test-api
```

#### 3. **Problemas de permisos con volúmenes**
```bash
# Verificar permisos de archivos montados
ls -la backend/tests/
ls -la backend/app/

# Ajustar permisos si es necesario
sudo chown -R $USER:$USER backend/tests/
sudo chown -R $USER:$USER backend/app/
```

#### 2. **Errores de base de datos**
```bash
# Verificar conexión
psql postgresql://test_user:test_password@localhost:5432/test_db -c "SELECT 1;"

# Resetear base de datos
cd backend/docker
docker compose down -v
docker compose up -d db
```

#### 3. **Problemas de dependencias**
```bash
# Reinstalar dependencias
cd backend
pip install -r requirements.txt --force-reinstall

# Verificar versiones
pip list | grep -E "(fastapi|pytest|sqlalchemy)"
```

#### 4. **Tests lentos**
```bash
# Ejecutar tests en paralelo
python3 -m pytest tests/ -n auto

# Ejecutar solo tests específicos
python3 -m pytest tests/test_api/test_auth.py -v
```

## 📚 Mejores Prácticas

### Estructura de Tests

```
backend/tests/
├── conftest.py              # Configuración global
├── test_validation_complete.py  # Tests de integración completos
├── test_validation_simple.py    # Tests básicos de servicios
├── test_api/                # Tests de API
│   ├── test_auth.py
│   ├── test_documents.py
│   └── test_search.py
├── test_services/           # Tests de servicios
│   └── test_storage_service.py
└── test_utils/              # Tests de utilidades
    └── test_security.py
```

### Convenciones de Naming

```python
# ✅ Correcto
def test_user_creation_success():
def test_document_upload_with_valid_file():
def test_api_returns_404_for_nonexistent_resource():

# ❌ Incorrecto
def test_user():
def test_document():
def test_api():
```

### Mejores Prácticas para Tests en Contenedores

#### 1. **Aislamiento de Tests**
```python
# ✅ Usar fixtures con cleanup automático
@pytest.fixture(scope="function")
def test_user(db_session, test_tenant):
    user = User(email=f"test_{uuid.uuid4().hex[:8]}@example.com", tenant_id=test_tenant.id)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    yield user

    # Cleanup automático
    db_session.delete(user)
    db_session.commit()
```

#### 2. **Configuración Específica para Contenedores**
```python
# ✅ Detectar si estamos en entorno de test
import os

def is_test_environment():
    return os.getenv("TESTING") == "true" or os.getenv("PYTEST_CURRENT_TEST")

# ✅ Usar URLs de servicios de test
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://test_user:test_password@test-db:5432/test_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://test-redis:6379")
```

#### 3. **Timeouts y Esperas**
```python
# ✅ Esperas inteligentes para servicios
def wait_for_service(url, timeout=30):
    import time
    import requests

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False
```

### Fixtures Recomendadas

```python
@pytest.fixture(scope="function")
def test_user(db_session, test_tenant):
    """Crear usuario de test con cleanup automático"""
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("password"),
        tenant_id=test_tenant.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    yield user

    # Cleanup
    db_session.delete(user)
    db_session.commit()
```

## 🚀 Próximos Pasos

### Mejoras Planificadas

1. **Tests de Performance Avanzados**
   - Load testing con Locust
   - Memory profiling
   - Database query optimization

2. **Tests de Seguridad Automatizados**
   - SQL injection tests
   - XSS prevention
   - Authentication bypass attempts

3. **Tests de UI/UX**
   - E2E tests con Playwright
   - Visual regression tests
   - Accessibility tests

4. **Integración Continua Avanzada**
   - Tests paralelos
   - Cache inteligente
   - Reportes en tiempo real

## 📞 Soporte

### Canales de Comunicación

- **Issues**: [GitHub Issues](https://github.com/your-org/nexusdocs360/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/nexusdocs360/discussions)
- **Slack**: #testing-channel

### Reportar Problemas

```markdown
## 🐛 Bug Report

**Descripción**: [Descripción clara del problema]

**Pasos para reproducir**:
1. [Paso 1]
2. [Paso 2]
3. [Paso 3]

**Resultado esperado**: [Qué debería pasar]

**Resultado actual**: [Qué está pasando]

**Entorno**:
- OS: [Ubuntu 20.04]
- Python: [3.9.7]
- Docker: [20.10.8]
- Branch: [main]

**Logs**:
```
[Incluir logs relevantes]
```

**Screenshots**: [Si aplica]
```

---

## 🎯 Checklist de Validación

### ✅ **Verificación de Tests en Contenedores**
- [ ] Docker y Docker Compose instalados correctamente
- [ ] `docker-compose.test.yml` configurado correctamente
- [ ] Servicios de test (PostgreSQL, Redis, Qdrant) funcionando
- [ ] Tests se ejecutan dentro del contenedor `test-api`
- [ ] Volúmenes montados correctamente (`tests/`, `app/`, `credentials/`)
- [ ] Variables de entorno de test configuradas
- [ ] Reportes de cobertura generados en `coverage_report/`

### ✅ **Validación del Sistema**
- [ ] Sistema levantado correctamente
- [ ] Servicios funcionando (12/13 disponibles)
- [ ] Tests de integración pasan dentro de contenedores
- [ ] Cobertura de código > 80%
- [ ] Tests de seguridad pasan
- [ ] Performance dentro de límites
- [ ] Reportes generados correctamente
- [ ] Cleanup automático funciona
- [ ] CI/CD configurado correctamente

### ✅ **Comandos de Verificación**
```bash
# Verificar configuración de Docker
docker --version && docker compose version

# Ejecutar tests básicos
cd backend/docker
docker compose -f docker-compose.test.yml run --rm test-api pytest tests/test_api/test_auth.py -v

# Verificar reportes
ls -la backend/coverage_report/
```

**Estado**: ✅ **VALIDACIÓN COMPLETA - TESTS EN CONTENEDORES**
