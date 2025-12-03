#!/bin/bash

# GPU-optimized startup script for Nexus Document Backend

set -e

echo "🚀 Starting Nexus Document Backend with GPU support..."
echo ""

# Check for NVIDIA GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo "⚠️  WARNING: nvidia-smi not found. GPU support may not work."
    echo "   Install NVIDIA drivers and nvidia-docker2 for GPU support."
    echo ""
fi

# Check for nvidia-docker
if ! docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
    echo "❌ ERROR: Docker GPU support not working!"
    echo "   Please install nvidia-docker2:"
    echo "   sudo apt-get install nvidia-docker2"
    echo "   sudo systemctl restart docker"
    exit 1
fi

echo "✅ GPU support detected!"
nvidia-smi --query-gpu=name,memory.total --format=csv

# Check if .env file exists
if [ ! -f "../.env" ]; then
    echo "❌ Error: .env file not found in backend root directory"
    exit 1
fi

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker compose down

# Build with GPU support
echo "🔨 Building with GPU support..."
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build

# Start services with GPU
echo "🎯 Starting services with GPU acceleration..."
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Start worker
echo "👷 Starting background-worker service..."
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d background-worker

# Wait for Ollama
echo "⏳ Waiting for Ollama to start with GPU..."
sleep 10

# Verify GPU is being used
echo "🔍 Verifying GPU usage in Ollama..."
docker compose exec -T ollama-service nvidia-smi 2>/dev/null || echo "GPU check failed"

# Download models
echo "📥 Ensuring models are available..."
docker compose exec -T ollama-service ollama pull all-minilm:latest || true
docker compose exec -T ollama-service ollama pull llama3.2 || true

echo ""
echo "✅ GPU-accelerated environment started!"
echo ""
echo "🚀 Performance benefits with GPU:"
echo "   • Embeddings: 5-10x faster"
echo "   • LLM inference: 3-5x faster"
echo "   • Multiple parallel requests supported"
echo ""
echo "📊 Monitor GPU usage:"
echo "   watch nvidia-smi"
echo "   docker compose exec ollama-service nvidia-smi"
echo ""
echo "🛑 Stop services:"
echo "   docker compose -f docker-compose.yml -f docker-compose.gpu.yml down"
