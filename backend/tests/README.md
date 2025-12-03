# 🧪 Backend Testing Suite - NexusDocs360

## 📋 Resumen

Suite completa de pruebas para el backend de NexusDocs360, incluyendo tests unitarios, de integración, performance y validación del sistema.

## 🎯 Tipos de Pruebas

### 1. **Tests Unitarios** (`pytest tests/`)
- Tests individuales de funciones y métodos
- Cobertura de código alta
- Ejecutan rápido sin dependencias externas

### 2. **Tests de Integración** (`test_validation_complete.py`)
- Tests de integración entre servicios
- Validación de APIs y bases de datos
- Tests end-to-end con datos reales

### 3. **Tests de Validación** (`validate_system.py`)
- Validación completa del sistema
- Checks de todos los servicios
- Reporte de estado general

### 4. **Tests de Servicios** (`test_validation_simple.py`)
- Validación de servicios individuales
- Health checks y conectividad
- Tests de infraestructura

## 🚀 Ejecución Rápida

### Usando el Script Principal

```bash
# Desde la raíz del proyecto
./run-tests.sh --quick          # Tests rápidos
./run-tests.sh --full           # Tests completos con Docker
./run-tests.sh --unit           # Solo tests unitarios
./run-tests.sh --integration    # Solo tests de integración
./run-tests.sh --performance    # Tests de performance
./run-tests.sh --coverage       # Con reporte de cobertura
./run-tests.sh --clean          # Limpiar entorno
./run-tests.sh --setup          # Configurar entorno
```

### Ejecución Manual

```bash
# Tests unitarios
cd backend
python3 -m pytest tests/ -v

# Tests con cobertura
python3 -m pytest tests/ -v --cov=app --cov-report=html

# Tests específicos
python3 -m pytest tests/test_api/test_auth.py -v
python3 -m pytest tests/test_services/ -v

# Tests de integración
cd tests
python3 test_validation_complete.py
python3 test_validation_simple.py

# Validación del sistema
cd ../..
python3 validate_system.py
```

## 📁 Estructura de Tests

```
backend/tests/
├── conftest.py              # Configuración global de pytest
├── test_validation_complete.py  # Tests de integración completos
├── test_validation_simple.py    # Tests básicos de servicios
├── run_validation_complete.py   # Ejecutor de tests de integración
├── run_tests.sh             # Script de ejecución completo
├── printf_colors.sh         # Utilidades de colores
├── test_api/                # Tests de API
│   ├── test_admin.py
│   ├── test_auth.py
│   ├── test_chat.py
│   ├── test_document_insights.py
│   ├── test_document_shares.py
│   ├── test_documents.py
│   ├── test_search.py
│   └── test_tenants.py
├── test_services/           # Tests de servicios
│   ├── test_document_service.py
│   ├── test_embedding_service.py
│   ├── test_storage_service.py
│   └── test_vector_service.py
└── test_utils/              # Tests de utilidades
    └── test_security.py
```

## 🔧 Configuración

### Variables de Entorno

```bash
# Archivo: backend/.env.test
ENVIRONMENT=test
DEBUG=true
SECRET_KEY=test-secret-key-for-testing-only

# Base de datos
DATABASE_URL=postgresql://test_user:test_password@localhost:5432/test_db
ASYNC_DATABASE_URL=postgresql+asyncpg://test_user:test_password@localhost:5432/test_db

# Redis
REDIS_URL=redis://localhost:6379/1

# Servicios externos
WEAVIATE_URL=http://localhost:8080
ELASTICSEARCH_URL=http://localhost:9200

# Clerk (test mode)
CLERK_SECRET_KEY=test-clerk-secret-key
CLERK_PUBLISHABLE_KEY=test-clerk-publishable-key

# Storage
USE_MOCK_STORAGE=true
TESTING=true
```

### Fixtures Disponibles

```python
# Usuario de test con tenant
@pytest.fixture
def test_user(db_session, test_tenant):
    # Crea usuario con datos únicos

# Superusuario
@pytest.fixture
def test_superuser(db_session, test_tenant):
    # Crea superusuario

# Documentos de test
@pytest.fixture
def test_documents(db_session, test_tenant, test_user):
    # Crea documentos de prueba

# Servicios mockeados
@pytest.fixture
def mock_elysia_service():
    # Mock del servicio LLM

@pytest.fixture
def mock_storage_service():
    # Mock del servicio de storage
```

## 📊 Reportes de Cobertura

### Generar Reportes

```bash
# Reporte HTML
cd backend
python3 -m pytest tests/ --cov=app --cov-report=html

# Reporte XML (para CI/CD)
python3 -m pytest tests/ --cov=app --cov-report=xml

# Reporte en terminal
python3 -m pytest tests/ --cov=app --cov-report=term
```

### Ver Reportes

```bash
# Abrir reporte HTML
open backend/htmlcov/index.html

# Ver resumen
python3 -m pytest tests/ --cov=app --cov-report=term-missing
```

## 🔄 CI/CD con GitHub Actions

### Workflows Disponibles

1. **PR Validation** (`.github/workflows/pr-validation.yml`)
   - ✅ Linting (Frontend & Backend)
   - ✅ Tests unitarios
   - ✅ Build check
   - ✅ Security scan

2. **Integration Tests** (`.github/workflows/integration-tests.yml`)
   - ✅ Tests de integración completos
   - ✅ Validación de servicios
   - ✅ Tests end-to-end
   - ✅ Reportes detallados

3. **Nightly Tests** (`.github/workflows/nightly-tests.yml`)
   - ✅ Tests completos con datos reales
   - ✅ Performance testing
   - ✅ Load testing básico

4. **Deployment Tests** (`.github/workflows/deployment-tests.yml`)
   - ✅ Smoke tests
   - ✅ Docker build validation
   - ✅ Infrastructure validation

### Ejecutar Workflows Manualmente

```bash
# Desde GitHub Actions tab
# Hacer click en "Run workflow" en el workflow deseado
```

## 🐛 Debugging y Troubleshooting

### Problemas Comunes

#### 1. **Tests fallan por servicios no disponibles**
```bash
# Verificar servicios
docker compose ps

# Reiniciar servicios
cd backend/docker
./start-dev.sh

# Verificar conectividad
python3 validate_system.py
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

## 📈 Métricas y KPIs

### Cobertura de Código
- **Objetivo**: > 80%
- **Actual**: Ver reporte de cobertura
- **Comando**: `python3 -m pytest tests/ --cov=app --cov-report=term`

### Tiempo de Ejecución
- **Tests unitarios**: < 5 minutos
- **Tests de integración**: < 10 minutos
- **Suite completa**: < 15 minutos

### Tasa de Éxito
- **Objetivo**: > 95%
- **Fallas aceptables**: Tests de servicios externos

## 🎯 Mejores Prácticas

### Estructura de Tests

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

### Tests Independientes

```python
# ✅ Cada test es independiente
def test_create_user(db_session):
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None

# ❌ Tests dependientes (evitar)
def test_create_user():
    # Crea usuario

def test_update_user():
    # Asume que test_create_user ya creó el usuario
```

### Cleanup Automático

```python
@pytest.fixture
def test_user(db_session, test_tenant):
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        tenant_id=test_tenant.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    yield user

    # Cleanup automático
    db_session.delete(user)
    db_session.commit()
```

## 🚀 Próximos Pasos

### Mejoras Planificadas

1. **Tests de UI/UX**
   - E2E tests con Playwright
   - Visual regression tests

2. **Tests de Seguridad Avanzados**
   - SQL injection tests
   - XSS prevention
   - Authentication bypass attempts

3. **Tests de Performance**
   - Load testing con Locust
   - Memory profiling
   - Database query optimization

4. **Integración Continua**
   - Tests paralelos avanzados
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

**Comando ejecutado**:
```
[Comando que causó el problema]
```

**Logs**:
```
[Incluir logs relevantes]
```

**Screenshots**: [Si aplica]
```

---

## ✅ Checklist de Testing

- [ ] Tests unitarios pasan
- [ ] Tests de integración pasan
- [ ] Cobertura de código > 80%
- [ ] Tests de performance pasan
- [ ] Tests de seguridad pasan
- [ ] CI/CD configurado correctamente
- [ ] Reportes generados correctamente
- [ ] Cleanup automático funciona
