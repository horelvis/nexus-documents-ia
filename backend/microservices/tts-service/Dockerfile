# TTS Service Dockerfile
# Uses NVIDIA CUDA for GPU-accelerated inference with VibeVoice

# Base image with CUDA support
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install Python and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    curl \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

# Set working directory
WORKDIR /app

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install PyTorch with CUDA support first (for better caching)
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install FlashAttention2 (required for GPU-accelerated VibeVoice)
# Using pre-built wheel from https://github.com/Dao-AILab/flash-attention/releases
# Note: Must match CUDA version (12.x) and PyTorch version
RUN pip install packaging ninja && \
    pip install flash-attn --no-build-isolation || \
    echo "FlashAttention2 installation failed, will use eager attention"

# Copy requirements and install dependencies
COPY requirements.txt .

# Install remaining dependencies
# Note: We install transformers with specific version for VibeVoice compatibility
RUN pip install --prefer-binary -r requirements.txt || \
    (echo "Some packages failed, installing core packages..." && \
     pip install fastapi uvicorn pydantic pydantic-settings httpx numpy scipy redis \
                 transformers==4.51.3 accelerate diffusers librosa soundfile \
                 google-cloud-texttospeech websockets)

# Copy application code
COPY app/ ./app/

# Create cache directory and non-root user for security
RUN mkdir -p /app/.cache/huggingface && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /opt/venv
USER appuser

# Environment variables for runtime
ENV PYTHONPATH=/app \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
