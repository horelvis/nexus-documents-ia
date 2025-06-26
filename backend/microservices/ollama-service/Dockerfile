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
# Set environment for GPU detection\n\
export NVIDIA_VISIBLE_DEVICES=all\n\
export NVIDIA_DRIVER_CAPABILITIES=compute,utility\n\
export CUDA_VISIBLE_DEVICES=0\n\
\n\
# Check for GPU availability\n\
if command -v nvidia-smi &> /dev/null; then\n\
    echo "GPU detected:"\n\
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader\n\
    export OLLAMA_GPU_LAYERS=999\n\
    export OLLAMA_CUDA=1\n\
else\n\
    echo "No GPU detected, using CPU"\n\
fi\n\
\n\
# Start Ollama server in background\n\
ollama serve &\n\
\n\
# Wait for Ollama to be ready\n\
echo "Waiting for Ollama to start..."\n\
sleep 10\n\
\n\
# Pull optimized models for your hardware\n\
if [ ! -d "/root/.ollama/models" ] || [ -z "$(ls -A /root/.ollama/models 2>/dev/null)" ]; then\n\
    echo "Pulling optimized models for high-end hardware..."\n\
    # Larger, more capable models for 64GB RAM + 42GB VRAM\n\
    ollama pull llama3.2\n\
    ollama pull all-minilm:latest\n\
    # Optional: pull nomic-embed-text as backup\n\
    # ollama pull nomic-embed-text\n\
    echo "Models downloaded successfully"\n\
else\n\
    echo "Models already exist, skipping download"\n\
fi\n\
\n\
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