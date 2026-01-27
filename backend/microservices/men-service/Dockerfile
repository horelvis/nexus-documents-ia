# MEN Service Dockerfile
# Mixture of Experts Network for Document Intelligence
#
# Base VRAM usage: ~4.0 GB (Orchestrator 1.5B + Modeler 3B @ 4-bit)
# Peak VRAM usage: ~4.5-5.0 GB (with Expert loaded)

FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

# Pip configuration for resilience
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=5 \
    PIP_NO_CACHE_DIR=0 \
    PYTHONWARNINGS="ignore::DeprecationWarning" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies
# Note: torch with CUDA requires specific installation
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cu121 && \
    pip install --prefer-binary -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create directories for experts
RUN mkdir -p /app/trained_experts/_generic_ && \
    mkdir -p /app/trained_experts/example_tenant

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Environment variables
ENV MEN_ENABLED=true \
    MEN_MODELER_ENABLED=true \
    MEN_EXPERTS_ENABLED=true \
    MEN_EXPERTS_DIR=/app/trained_experts \
    MEN_ORCHESTRATOR_MODEL=Qwen/Qwen2.5-1.5B-Instruct \
    MEN_MODELER_MODEL=Qwen/Qwen2.5-3B-Instruct \
    MEN_EXPERT_BASE_MODEL=Qwen/Qwen2.5-0.5B-Instruct \
    LOG_LEVEL=INFO

# Expose port
EXPOSE 8010

# Health check
HEALTHCHECK --interval=60s --timeout=30s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8010/health || exit 1

# Run the service
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
