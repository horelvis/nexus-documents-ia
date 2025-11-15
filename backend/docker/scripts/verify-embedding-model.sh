#!/bin/bash

# Script to verify embedding model configuration

echo "🔍 Verifying Embedding Model Configuration..."
echo ""

API_KEY="${MICROSERVICES_API_KEY:?MICROSERVICES_API_KEY not set}"

# 1. Check if containers are running
echo "1️⃣ Checking container status..."
docker compose ps | grep -E "ollama-service|cag-service|api" | head -5

# 2. Check Ollama models
echo ""
echo "2️⃣ Checking available models in Ollama..."
docker compose exec -T ollama-service ollama list 2>/dev/null || echo "Failed to list models"

# 3. Check environment variables
echo ""
echo "3️⃣ Checking embedding model configuration..."
echo "In Ollama container:"
docker compose exec -T ollama-service sh -c 'echo "OLLAMA_EMBEDDING_MODEL=$OLLAMA_EMBEDDING_MODEL"'
docker compose exec -T ollama-service sh -c 'echo "EMBEDDING_MODEL=$EMBEDDING_MODEL"'

echo ""
echo "In CAG service:"
docker compose exec -T cag-service sh -c 'echo "EMBEDDING_MODEL=$EMBEDDING_MODEL"'

# 4. Test embedding generation
echo ""
echo "4️⃣ Testing embedding generation via CAG..."
curl -X POST http://localhost:8008/api/v1/cag/embeddings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d '["This is a test for embedding generation with GPU acceleration"]' \
  2>/dev/null | jq -r '.embeddings[0][:5]' 2>/dev/null || echo "Embedding test failed"

# 5. Check GPU usage
echo ""
echo "5️⃣ Checking GPU utilization..."
docker compose exec -T ollama-service nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv,noheader 2>/dev/null || echo "GPU monitoring not available"

# 6. Test embedding speed
echo ""
echo "6️⃣ Testing embedding generation speed..."
echo "Generating embedding for a sample text..."
START_TIME=$(date +%s.%N)
curl -X POST http://localhost:8008/api/v1/cag/embeddings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d '["Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."]' \
  > /dev/null 2>&1
END_TIME=$(date +%s.%N)
ELAPSED=$(echo "$END_TIME - $START_TIME" | bc)
echo "Embedding generation took: ${ELAPSED} seconds"

echo ""
echo "✅ Verification complete!"
echo ""
echo "📊 Expected performance with all-minilm + GPU:"
echo "   • Embedding generation: <0.1 seconds"
echo "   • GPU memory usage: ~200MB"
echo "   • 5-10x faster than CPU"
