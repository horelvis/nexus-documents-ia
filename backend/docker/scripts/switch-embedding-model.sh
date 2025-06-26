#!/bin/bash

echo "🔄 Switching to faster embedding model (all-minilm)..."

# 1. Download the new model
echo "📥 Downloading all-minilm model..."
docker compose exec -T ollama-service ollama pull all-minilm:latest

# 2. Remove old model to save space (optional)
echo "🗑️  Removing old nomic-embed-text model (optional)..."
docker compose exec -T ollama-service ollama rm nomic-embed-text 2>/dev/null || echo "Old model not found or in use"

# 3. Restart services
echo "🔄 Restarting services with new configuration..."
docker compose restart langchain-service ollama-service api

# 4. Wait for services
echo "⏳ Waiting for services to be ready..."
sleep 10

# 5. Show model info
echo "📊 Model comparison:"
echo ""
echo "Old model (nomic-embed-text):"
echo "  - Size: ~274MB"
echo "  - Dimensions: 768"
echo "  - Speed: Slower"
echo ""
echo "New model (all-minilm):"
echo "  - Size: ~46MB (6x smaller!)"
echo "  - Dimensions: 384"
echo "  - Speed: Much faster (3-5x)"
echo "  - Quality: Good for most use cases"
echo ""
echo "✅ Model switch complete!"
echo ""
echo "⚠️  Note: Existing documents will keep their old embeddings."
echo "   Only new documents will use the faster model."
echo "   To re-index existing documents, use the re-index script."