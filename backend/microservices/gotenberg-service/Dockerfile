# Multi-stage build for production
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies for PDF processing and Gotenberg
RUN apt-get update && apt-get install -y \
    poppler-utils \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Gotenberg
RUN wget -O /usr/local/bin/gotenberg https://github.com/gotenberg/gotenberg/releases/download/v8.0.3/gotenberg_8.0.3_linux_amd64 \
    && chmod +x /usr/local/bin/gotenberg

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/pip /usr/local/bin/

# Copy application code
COPY app/ ./app/

# Copy start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Create non-root user
RUN useradd --create-home --shell /bin/bash gotenberg \
    && chown -R gotenberg:gotenberg /app

USER gotenberg

# Expose port
EXPOSE 8005

# Run both Gotenberg and the application
CMD ["/start.sh"]