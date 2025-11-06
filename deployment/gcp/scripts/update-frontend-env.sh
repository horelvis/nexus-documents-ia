#!/bin/bash
# Update frontend environment variables only

set -e

echo "🔧 Actualizando variables de entorno del frontend"
echo "=============================================="
echo ""

# 1. Ver variables actuales
echo "1️⃣ Variables actuales del frontend:"
gcloud run services describe nexus-frontend-pre \
    --region=europe-west1 \
    --project=nexusdocs360-pre \
    --format="value(spec.template.spec.containers[0].env[].name,spec.template.spec.containers[0].env[].value)" | grep -E "NEXT_PUBLIC|CLERK" || echo "No se pudieron obtener"

# 2. Actualizar variables
echo ""
echo "2️⃣ Actualizando variables de entorno..."
gcloud run services update nexus-frontend-pre \
    --update-env-vars "NEXT_PUBLIC_API_URL=https://pre-api.nexusdocs360.app,NEXT_PUBLIC_APP_URL=https://pre.nexusdocs360.app" \
    --region=europe-west1 \
    --project=nexusdocs360-pre

echo ""
echo "3️⃣ Esperando actualización del servicio..."
echo "Esto puede tardar 1-2 minutos..."
sleep 30

# 3. Verificar nuevas variables
echo ""
echo "4️⃣ Nuevas variables del frontend:"
gcloud run services describe nexus-frontend-pre \
    --region=europe-west1 \
    --project=nexusdocs360-pre \
    --format="value(spec.template.spec.containers[0].env[].name,spec.template.spec.containers[0].env[].value)" | grep -E "NEXT_PUBLIC|CLERK"

# 4. Test
echo ""
echo "5️⃣ Probando frontend..."
echo ""
echo "Verificando redirect:"
curl -s -I https://pre.nexusdocs360.app | grep -i location || echo "✅ No hay redirect"

echo ""
echo "✅ Variables actualizadas!"
echo ""
echo "NOTA: Cloud Run puede tardar 2-3 minutos en aplicar completamente los cambios."
echo "Si el frontend sigue redirigiendo, espera un poco más."