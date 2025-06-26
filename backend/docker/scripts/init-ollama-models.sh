#!/bin/bash

# Script to initialize Ollama with required models

echo "Initializing Ollama models..."

# Wait for Ollama to be ready
echo "Waiting for Ollama service to be ready..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    echo "Waiting for Ollama to start..."
    sleep 2
done

echo "Ollama is ready. Pulling required models..."

# Pull the embedding model
echo "Pulling nomic-embed-text model..."
docker compose exec ollama-service ollama pull nomic-embed-text

# Pull the LLM model
echo "Pulling llama3.2 model..."
docker compose exec ollama-service ollama pull llama3.2

# List all available models
echo "Available models:"
docker compose exec ollama-service ollama list

echo "Ollama initialization complete!"