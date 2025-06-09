#!/bin/bash
echo "🧹 Limpiando contenedores y cache..."

# Parar contenedores
docker-compose down --remove-orphans

# Limpiar cache de Python
find backend/ -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find backend/ -name "*.pyc" -delete 2>/dev/null || true

# Limpiar Docker
docker system prune -f

echo "🔨 Reconstruyendo sin cache..."
docker-compose build --no-cache backend

echo "🚀 Iniciando servicios..."
docker-compose up