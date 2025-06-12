# Build Python app
FROM python:3.11-slim as python-app

WORKDIR /app

# Install system dependencies for PDF processing
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Final stage - use Gotenberg as base and add Python app
FROM gotenberg/gotenberg:8

USER root

# Copy Python and dependencies from python-app stage
COPY --from=python-app /usr/local /usr/local
COPY --from=python-app /app /app

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Create app user and fix permissions
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app

USER app

WORKDIR /app

# Expose ports (Gotenberg on 3000, FastAPI on 8005)
EXPOSE 3000 8005

CMD ["/start.sh"]