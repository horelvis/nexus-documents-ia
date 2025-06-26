#!/bin/bash

echo "🔧 Fixing document indexing issues..."

# 1. Ensure Ollama has the embedding model
echo "📥 Ensuring fast embedding model is available..."
docker compose exec -T ollama-service ollama pull all-minilm:latest

# 2. Restart services to clear any stuck connections
echo "🔄 Restarting services..."
docker compose restart ollama-service langchain-service api

# 3. Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# 4. Check Ollama models
echo "📋 Available Ollama models:"
docker compose exec -T ollama-service ollama list

# 5. Test embedding generation
echo "🧪 Testing embedding generation..."
docker compose exec -T ollama-service curl -X POST http://localhost:11434/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "all-minilm",
    "prompt": "test embedding generation"
  }' | head -c 200

echo ""
echo "✅ Indexing fix complete. Try uploading a document again."
echo ""
echo "💡 Tips:"
echo "   - For large documents, indexing may take 30-60 seconds"
echo "   - Check logs: docker compose logs -f api langchain-service"
echo "   - If still failing, check RAM usage: docker stats"