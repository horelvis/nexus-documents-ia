#!/bin/bash
# Fix backend errors in Cloud Run deployment

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-backend-pre"

echo "🔧 Fixing Backend Errors in Cloud Run"
echo "===================================="
echo ""

# 1. Get current configuration
echo "1️⃣ Getting current configuration..."
echo ""

# Get Redis instance IP
echo "Getting Redis IP..."
REDIS_IP=$(gcloud redis instances describe nexus-redis-pre \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(host)" 2>/dev/null || echo "")

if [ -z "$REDIS_IP" ]; then
    echo "⚠️  Redis instance not found. Creating Redis instance..."
    gcloud redis instances create nexus-redis-pre \
        --size=1 \
        --region=$REGION \
        --redis-version=redis_7_0 \
        --project=$PROJECT_ID
    
    # Wait for Redis to be ready
    echo "Waiting for Redis instance to be ready..."
    sleep 60
    
    REDIS_IP=$(gcloud redis instances describe nexus-redis-pre \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(host)")
fi

echo "Redis IP: $REDIS_IP"

# 2. Create/Update secrets
echo ""
echo "2️⃣ Creating/Updating secrets..."

# Check if .env.pre exists
if [ -f "$(dirname "$0")/../.env.pre" ]; then
    source "$(dirname "$0")/../.env.pre"
else
    echo "⚠️  .env.pre not found. Using defaults..."
fi

# Create Redis URL secret
echo "Creating Redis URL secret..."
echo "redis://${REDIS_IP}:6379/0" | gcloud secrets create redis-url-pre \
    --data-file=- \
    --project=$PROJECT_ID 2>/dev/null || \
echo "redis://${REDIS_IP}:6379/0" | gcloud secrets versions add redis-url-pre \
    --data-file=- \
    --project=$PROJECT_ID

# Create Stripe secrets if not exist
if [ -n "$STRIPE_SECRET_KEY" ]; then
    echo "Creating Stripe secrets..."
    echo "$STRIPE_SECRET_KEY" | gcloud secrets create stripe-secret-key-pre \
        --data-file=- \
        --project=$PROJECT_ID 2>/dev/null || \
    echo "$STRIPE_SECRET_KEY" | gcloud secrets versions add stripe-secret-key-pre \
        --data-file=- \
        --project=$PROJECT_ID
    
    echo "$STRIPE_PUBLISHABLE_KEY" | gcloud secrets create stripe-publishable-key-pre \
        --data-file=- \
        --project=$PROJECT_ID 2>/dev/null || \
    echo "$STRIPE_PUBLISHABLE_KEY" | gcloud secrets versions add stripe-publishable-key-pre \
        --data-file=- \
        --project=$PROJECT_ID
    
    if [ -n "$STRIPE_WEBHOOK_SECRET" ]; then
        echo "$STRIPE_WEBHOOK_SECRET" | gcloud secrets create stripe-webhook-secret-pre \
            --data-file=- \
            --project=$PROJECT_ID 2>/dev/null || \
        echo "$STRIPE_WEBHOOK_SECRET" | gcloud secrets versions add stripe-webhook-secret-pre \
            --data-file=- \
            --project=$PROJECT_ID
    fi
else
    echo "⚠️  STRIPE_SECRET_KEY not found in .env.pre"
    # Create dummy secrets for now
    echo "sk_test_dummy" | gcloud secrets create stripe-secret-key-pre \
        --data-file=- \
        --project=$PROJECT_ID 2>/dev/null || echo "Secret already exists"
fi

# Create other required secrets
echo "Creating other required secrets..."

# GCS bucket name
GCS_BUCKET="${GCS_BUCKET_NAME:-nexusdocs360-pre-storage}"
echo "$GCS_BUCKET" | gcloud secrets create gcs-bucket-name-pre \
    --data-file=- \
    --project=$PROJECT_ID 2>/dev/null || \
echo "$GCS_BUCKET" | gcloud secrets versions add gcs-bucket-name-pre \
    --data-file=- \
    --project=$PROJECT_ID

# Get Cloud SQL instance connection name
CLOUD_SQL_INSTANCE=$(gcloud sql instances describe nexus-db-pre \
    --project=$PROJECT_ID \
    --format="value(connectionName)")

echo "Cloud SQL instance: $CLOUD_SQL_INSTANCE"

# 3. Update Cloud Run service with all environment variables and secrets
echo ""
echo "3️⃣ Updating Cloud Run service configuration..."

gcloud run services update $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --update-secrets="\
DATABASE_URL=database-url-pre:latest,\
POSTGRES_SERVER=postgres-server-pre:latest,\
POSTGRES_USER=postgres-user-pre:latest,\
POSTGRES_PASSWORD=postgres-password-pre:latest,\
POSTGRES_DB=postgres-db-pre:latest,\
REDIS_URL=redis-url-pre:latest,\
CLERK_SECRET_KEY=clerk-secret-pre:latest,\
CLERK_PUBLISHABLE_KEY=clerk-publishable-key-pre:latest,\
CLERK_JWT_VERIFICATION_KEY=clerk-jwt-verification-key-pre:latest,\
STRIPE_SECRET_KEY=stripe-secret-key-pre:latest,\
STRIPE_PUBLISHABLE_KEY=stripe-publishable-key-pre:latest,\
GCS_BUCKET_NAME=gcs-bucket-name-pre:latest" \
    --update-env-vars="\
ENVIRONMENT=pre,\
PYTHONUNBUFFERED=1,\
REDIS_HOST=$REDIS_IP,\
REDIS_PORT=6379,\
GCS_PROJECT_ID=$PROJECT_ID,\
BACKEND_CORS_ORIGINS=*,\
SERVER_HOST=0.0.0.0,\
MICROSERVICE_LANGCHAIN_URL=https://langchain-service-pre-300252412370.europe-west1.run.app,\
MICROSERVICE_LANGROID_URL=https://langroid-service-pre-300252412370.europe-west1.run.app,\
MICROSERVICE_STORAGE_URL=https://storage-service-pre-300252412370.europe-west1.run.app,\
MICROSERVICE_OLLAMA_URL=https://ollama-service-pre-300252412370.europe-west1.run.app" \
    --add-cloudsql-instances=$CLOUD_SQL_INSTANCE

echo ""
echo "Waiting for service to be ready..."
sleep 30

# 4. Test the service
echo ""
echo "4️⃣ Testing the service..."
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(status.url)")

echo "Service URL: $SERVICE_URL"
echo ""

# Test health endpoint
echo "Testing health endpoint..."
curl -s "$SERVICE_URL/health" | jq . || echo "Failed to get health status"

echo ""
echo "Testing through custom domain..."
curl -s "https://pre-api.nexusdocs360.app/health" | jq . || echo "Failed through custom domain"

# 5. Check logs for errors
echo ""
echo "5️⃣ Recent error logs:"
echo ""
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME AND severity>=ERROR" \
    --limit=20 \
    --project=$PROJECT_ID \
    --format="table(timestamp,jsonPayload.message)"

echo ""
echo "✅ Backend configuration updated!"
echo ""
echo "Summary:"
echo "- Redis configured at: $REDIS_IP:6379"
echo "- Cloud SQL connected via: $CLOUD_SQL_INSTANCE"
echo "- All required secrets mounted"
echo "- Environment variables set"
echo ""
echo "If you still see errors, check:"
echo "1. Stripe API keys are valid (currently using test/dummy keys)"
echo "2. Cloud SQL allows connections from Cloud Run"
echo "3. Redis instance is in the same VPC or properly configured"
echo "4. All microservices are deployed and running"