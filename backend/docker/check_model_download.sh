#!/bin/bash

echo "Verificando estado de descarga del modelo gpt-oss:20b..."
echo "============================================="

while true; do
    # Verificar si el modelo está en la lista
    if docker exec docker-genai-ollama-1 ollama list 2>/dev/null | grep -q "gpt-oss:20b"; then
        echo "✓ Modelo gpt-oss:20b descargado exitosamente!"
        docker exec docker-genai-ollama-1 ollama list | grep gpt-oss
        break
    else
        # Verificar si el proceso de descarga está activo
        if docker exec docker-genai-ollama-1 sh -c "ps aux | grep 'ollama pull' | grep -v grep" &>/dev/null; then
            echo "⏳ Descarga en progreso... ($(date '+%H:%M:%S'))"
            sleep 30
        else
            echo "⚠️  No se detecta descarga activa. Verificando estado..."
            if docker exec docker-genai-ollama-1 ollama list 2>/dev/null | grep -q "gpt-oss"; then
                echo "✓ Modelo encontrado!"
                docker exec docker-genai-ollama-1 ollama list | grep gpt-oss
                break
            else
                echo "✗ El modelo no está descargado y no hay descarga activa."
                echo "Para iniciar la descarga manualmente, ejecute:"
                echo "  docker exec docker-genai-ollama-1 ollama pull gpt-oss:20b"
                exit 1
            fi
        fi
    fi
done

echo ""
echo "Configuración actual en .env:"
grep "LLM_MODEL\|DEFAULT_LLM_MODEL" /home/nexus/git/nexus-documents-ia/backend/.env | head -5