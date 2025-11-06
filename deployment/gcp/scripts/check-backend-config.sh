#!/bin/bash
# Check backend configuration and connectivity

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-backend-pre"

echo "🔍 Checking Backend Configuration"
echo "================================"
echo ""

# 1. Check if all required secrets exist
echo "1️⃣ Checking secrets..."
echo ""

REQUIRED_SECRETS=(
    "database-url-pre"
    "postgres-server-pre"
    "postgres-user-pre"
    "postgres-password-pre"
    "postgres-db-pre"
    "redis-url-pre"
    "clerk-secret-pre"
    "clerk-publishable-key-pre"
    "clerk-jwt-verification-key-pre"
    "stripe-secret-key-pre"
    "stripe-publishable-key-pre"
    "gcs-bucket-name-pre"
)

MISSING_SECRETS=()

for secret in "${REQUIRED_SECRETS[@]}"; do
    if gcloud secrets describe $secret --project=$PROJECT_ID &>/dev/null; then
        echo "✅ $secret exists"
    else
        echo "❌ $secret is missing"
        MISSING_SECRETS+=($secret)
    fi
done

if [ ${#MISSING_SECRETS[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  Missing secrets: ${MISSING_SECRETS[*]}"
    echo ""
fi

# 2. Check Redis instance
echo ""
echo "2️⃣ Checking Redis instance..."
REDIS_INFO=$(gcloud redis instances describe nexus-redis-pre \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="table(name,state,host,port)" 2>/dev/null || echo "Redis instance not found")
echo "$REDIS_INFO"

# 3. Check Cloud SQL instance
echo ""
echo "3️⃣ Checking Cloud SQL instance..."
SQL_INFO=$(gcloud sql instances describe nexus-db-pre \
    --project=$PROJECT_ID \
    --format="table(name,state,ipAddresses[0].ipAddress,connectionName)" 2>/dev/null || echo "Cloud SQL instance not found")
echo "$SQL_INFO"

# 4. Check Cloud Run service configuration
echo ""
echo "4️⃣ Checking Cloud Run service configuration..."
echo ""

# Get environment variables
echo "Environment variables:"
gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(spec.template.spec.containers[0].env[].name,spec.template.spec.containers[0].env[].value)" | grep -E "REDIS|STRIPE|POSTGRES|GCS" | head -20

echo ""
echo "Mounted secrets:"
gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(spec.template.spec.containers[0].env[].valueFrom.secretKeyRef.name)" | head -20

# 5. Test connectivity
echo ""
echo "5️⃣ Testing service health..."
echo ""

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(status.url)")

echo "Direct Cloud Run URL: $SERVICE_URL"
HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/health" 2>/dev/null || echo "{}")
echo "$HEALTH_RESPONSE" | jq . 2>/dev/null || echo "$HEALTH_RESPONSE"

echo ""
echo "Custom domain: https://pre-api.nexusdocs360.app"
CUSTOM_HEALTH=$(curl -s "https://pre-api.nexusdocs360.app/health" 2>/dev/null || echo "{}")
echo "$CUSTOM_HEALTH" | jq . 2>/dev/null || echo "$CUSTOM_HEALTH"

# 6. Check recent logs
echo ""
echo "6️⃣ Recent error logs (last 10):"
echo ""
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME AND (textPayload=~\"ERROR|CRITICAL|Traceback|Exception\")" \
    --limit=10 \
    --project=$PROJECT_ID \
    --format="table(timestamp,textPayload)" 2>/dev/null || echo "No recent errors found"

echo ""
echo "✅ Configuration check complete"