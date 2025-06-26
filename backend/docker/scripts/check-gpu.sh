#!/bin/bash

echo "🔍 Checking GPU support for Ollama..."
echo ""

# 1. Check if nvidia-docker is installed
echo "1️⃣ Checking Docker GPU support..."
if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
    echo "✅ Docker GPU support is working"
else
    echo "❌ Docker GPU support NOT working. Install nvidia-docker2:"
    echo "   sudo apt-get install nvidia-docker2"
    echo "   sudo systemctl restart docker"
fi

# 2. Check GPU in Ollama container
echo ""
echo "2️⃣ Checking GPU in Ollama container..."
docker compose exec ollama-service nvidia-smi 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ GPU detected in Ollama container"
else
    echo "❌ GPU NOT detected in Ollama container"
fi

# 3. Check Ollama GPU usage
echo ""
echo "3️⃣ Checking Ollama GPU configuration..."
docker compose exec ollama-service sh -c 'echo "GPU Layers: $OLLAMA_GPU_LAYERS"'
docker compose exec ollama-service sh -c 'echo "CUDA Enabled: $OLLAMA_CUDA"'
docker compose exec ollama-service sh -c 'echo "CUDA Devices: $CUDA_VISIBLE_DEVICES"'

# 4. Test model loading with GPU
echo ""
echo "4️⃣ Testing model loading with GPU..."
docker compose exec ollama-service ollama run all-minilm:latest "test" 2>&1 | grep -E "gpu|cuda|layers" | head -5

# 5. Check current resource usage
echo ""
echo "5️⃣ Current GPU usage (if available):"
docker compose exec ollama-service nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || echo "GPU monitoring not available"

echo ""
echo "📊 Recommendations:"
echo "   - For embeddings, GPU provides 5-10x speedup"
echo "   - all-minilm model should use ~200MB GPU memory"
echo "   - Monitor GPU usage during indexing with: watch nvidia-smi"
echo ""
echo "🔧 To force GPU usage, restart Ollama:"
echo "   docker compose restart ollama-service"