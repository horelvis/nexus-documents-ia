#!/bin/bash
# tests/run_tests.sh

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Configurar variables de entorno para tests
export POSTGRES_SERVER="localhost"
export POSTGRES_USER="test_user"
export POSTGRES_PASSWORD="test_password"
export POSTGRES_DB="test_db"
export GCS_BUCKET_NAME="test-bucket"
export OLLAMA_BASE_URL="http://localhost:11434"

# Ejecutar tests con cobertura
pytest -xvs --cov=app --cov-report=term-missing --cov-report=html:coverage_report

# Mostrar resultado
echo "Test completados. El reporte de cobertura está disponible en coverage_report/index.html"