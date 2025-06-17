FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and setuptools
RUN pip install --no-cache-dir --upgrade pip==24.0 setuptools wheel

# Install dependencies in stages to handle complex dependencies
# First install pydantic and core dependencies
RUN pip install --no-cache-dir \
    pydantic==2.7.4 \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    pydantic-settings==2.1.0

# Then install langchain core
RUN pip install --no-cache-dir \
    langchain-core==0.2.23 \
    langsmith==0.1.93

# Install remaining requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/


# APLICAR EL PARCHE después de instalar
RUN python app/patch/patch_litellm.py


# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8007

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]