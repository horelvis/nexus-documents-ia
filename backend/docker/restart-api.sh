#!/bin/bash

echo "🔄 Reiniciando contenedor API para aplicar correcciones..."

# Restart only the API container
docker compose restart api

# Wait a bit for startup
echo "⏳ Esperando que el servicio se inicie..."
sleep 5

# Show recent logs
echo ""
echo "📋 Logs recientes del API:"
docker compose logs api --tail=50 | grep -E "(Verificando tabla subscriptions|plan_id|stripe_plan_id|✅|❌|🔧)"

echo ""
echo "✅ Reinicio completado!"