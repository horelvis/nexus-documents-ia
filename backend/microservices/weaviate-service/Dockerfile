FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
# Be resilient to slow PyPI: increase timeout and retries, prefer wheels
# Suppress known deprecation warnings from third-party libraries
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONWARNINGS="ignore::DeprecationWarning:httpx._models,ignore::DeprecationWarning:spacy.cli._util,ignore::DeprecationWarning:pydantic"
# --pre allows installing beta versions (agent-framework is in preview)
RUN pip install --prefer-binary --pre -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy agent prompt configuration files
COPY config/ ./config/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8007/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007", "--reload"]
