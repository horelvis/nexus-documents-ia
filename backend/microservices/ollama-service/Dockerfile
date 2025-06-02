FROM ollama/ollama:latest as ollama-base

# Install Python and dependencies for the API wrapper
FROM python:3.11-slim

# Install required system packages
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Ollama binary from the base image
COPY --from=ollama-base /bin/ollama /bin/ollama

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create ollama data directory
RUN mkdir -p /root/.ollama

# Expose ports
EXPOSE 11434 8000

# Create startup script
RUN echo '#!/bin/bash\n\
# Start Ollama server in background\n\
ollama serve &\n\
# Wait for Ollama to be ready\n\
sleep 5\n\
# Pull default models if they do not exist\n\
if [ ! -d "/root/.ollama/models" ]; then\n\
    echo "Pulling default models..."\n\
    ollama pull llama3.2:3b\n\
    ollama pull codellama:7b\n\
fi\n\
# Start the Python API wrapper\n\
python -m app.main\n\
' > /app/start.sh && chmod +x /app/start.sh

# Set environment variables
ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_PORT=11434
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:11434/api/tags || exit 1

# Start services
CMD ["/app/start.sh"]