# Emma Agent Service Dockerfile
# Intelligent AI agent service for document analysis and question answering

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies + Docker CLI (for ephemeral CENDOJ agent containers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
# Note: litellm is pinned in requirements.txt to block compromised versions
# (SNYK-PYTHON-LITELLM-15762713). See backend/security-constraints.txt for details.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
# ARG DOCKER_GID allows matching the host's docker socket group at build time
ARG DOCKER_GID=988
RUN useradd --create-home --shell /bin/bash appuser && \
    groupadd -g ${DOCKER_GID} dockerhost || true && \
    usermod -aG dockerhost appuser && \
    chown -R appuser:appuser /app && \
    mkdir -p /tmp/fastembed_cache /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /tmp/fastembed_cache /home/appuser/.cache/huggingface
USER appuser

# Set cache directories for appuser
ENV HF_HOME=/home/appuser/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/tmp/fastembed_cache

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Expose port
EXPOSE 8009

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8009/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
