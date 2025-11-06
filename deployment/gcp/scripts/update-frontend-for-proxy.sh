#!/bin/bash
# Update frontend Cloud Run service to work with proxy

set -e

echo "🔧 Updating Frontend for Proxy Support"
echo "====================================="
echo ""

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-frontend-pre"

echo "1️⃣ Current frontend configuration:"
gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(spec.template.spec.containers[0].env[].name)" | grep -E "NEXT_PUBLIC|URL" || echo "No URL env vars found"

echo ""
echo "2️⃣ Updating frontend with proxy-aware configuration..."

# Update the frontend to know its public URL
gcloud run services update $SERVICE_NAME \
    --update-env-vars="NEXT_PUBLIC_URL=https://pre.nexusdocs360.app,NEXT_PUBLIC_API_URL=https://pre-api.nexusdocs360.app,NEXTAUTH_URL=https://pre.nexusdocs360.app" \
    --region=$REGION \
    --project=$PROJECT_ID

echo ""
echo "⏳ Waiting for deployment..."
sleep 30

echo ""
echo "3️⃣ Testing frontend through proxy..."
response=$(curl -s -o /dev/null -w "%{http_code}" -L https://pre.nexusdocs360.app/)
echo "Frontend response: HTTP $response"

if [ "$response" = "200" ]; then
    echo "✅ Frontend is working through proxy!"
else
    echo "⚠️  Frontend returned $response"
    echo ""
    echo "Checking if it's still redirecting:"
    curl -I https://pre.nexusdocs360.app/ 2>&1 | grep -E "HTTP/|Location:" | head -10
fi

echo ""
echo "✅ Frontend updated for proxy support!"
echo ""
echo "The frontend now knows it's being accessed via:"
echo "- Public URL: https://pre.nexusdocs360.app"
echo "- API URL: https://pre-api.nexusdocs360.app"