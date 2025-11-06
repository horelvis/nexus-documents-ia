FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configurar entorno
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copiar archivo de requisitos desde el directorio padre
COPY ../requirements.txt .
COPY ../pyproject.toml .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Verificar que uvicorn está instalado
RUN pip show uvicorn || pip install uvicorn

# Copiar código fuente desde el directorio padre
COPY ../app ./app
COPY ../scripts ./scripts
COPY ../alembic ./alembic

# Crear directorio de credenciales
RUN mkdir -p /app/credentials

# Exponer puerto
EXPOSE 8000

# Comando para desarrollo con recarga automática
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app"]