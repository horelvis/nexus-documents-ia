#!/bin/bash
# Deploy Backend to Cloud Run - Complete Setup
# This script deploys the backend service with all required configurations

set -e

echo "🚀 Deploying Backend to Cloud Run"
echo "================================="
echo ""

# Configuration
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-backend-pre"
SERVICE_ACCOUNT="nexus-cloud-run-pre@${PROJECT_ID}.iam.gserviceaccount.com"

# Check authentication
echo "1️⃣ Checking authentication..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated. Please run: gcloud auth login"
    exit 1
fi

gcloud config set project $PROJECT_ID

# Enable required APIs
echo ""
echo "2️⃣ Enabling required APIs..."
gcloud services enable compute.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    --project=$PROJECT_ID

# Create service account if it doesn't exist
echo ""
echo "3️⃣ Setting up service account..."
if ! gcloud iam service-accounts describe $SERVICE_ACCOUNT --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "Creating service account..."
    gcloud iam service-accounts create nexus-cloud-run-pre \
        --display-name="Nexus Cloud Run Service Account (PRE)" \
        --project=$PROJECT_ID
fi

# Grant necessary roles
echo "Granting roles to service account..."
for role in \
    "roles/secretmanager.secretAccessor" \
    "roles/storage.admin" \
    "roles/cloudsql.client" \
    "roles/logging.logWriter" \
    "roles/monitoring.metricWriter"; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SERVICE_ACCOUNT" \
        --role="$role" \
        --condition=None --quiet || echo "Role $role might already be assigned"
done

# Deploy Cloud Run service (initial deployment or update)
echo ""
echo "4️⃣ Deploying Cloud Run service..."

# Get the latest image from Artifact Registry
IMAGE=$(gcloud artifacts docker images list \
    ${REGION}-docker.pkg.dev/${PROJECT_ID}/nexus-backend/backend \
    --include-tags \
    --format="value(IMAGE)" \
    --limit=1 | head -1)

if [ -z "$IMAGE" ]; then
    echo "❌ No Docker image found in Artifact Registry"
    echo "Please ensure GitHub Actions has built and pushed the image"
    exit 1
fi

echo "Using image: $IMAGE"

# Deploy with all configurations
gcloud run deploy $SERVICE_NAME \
    --image=$IMAGE \
    --region=$REGION \
    --project=$PROJECT_ID \
    --platform=managed \
    --allow-unauthenticated \
    --service-account=$SERVICE_ACCOUNT \
    --memory=8Gi \
    --cpu=4 \
    --min-instances=1 \
    --max-instances=20 \
    --concurrency=200 \
    --timeout=300 \
    --set-env-vars="ENVIRONMENT=pre,PORT=8000,WEB_CONCURRENCY=4,GUNICORN_WORKERS=4,GUNICORN_TIMEOUT=300" \
    --update-env-vars="GCS_BUCKET_NAME=nexusdocs360-pre-docs-eu"

# Update with all required secrets
echo ""
echo "5️⃣ Configuring secrets..."
SECRETS="POSTGRES_SERVER=postgres-server-pre:latest"
SECRETS+=",POSTGRES_USER=postgres-user-pre:latest"
SECRETS+=",POSTGRES_PASSWORD=postgres-password-pre:latest"
SECRETS+=",POSTGRES_DB=postgres-db-pre:latest"
SECRETS+=",DATABASE_URL=database-url-pre:latest"
SECRETS+=",ASYNC_DATABASE_URL=async-database-url-pre:latest"
SECRETS+=",SQLALCHEMY_DATABASE_URI=sqlalchemy-database-uri-pre:latest"
SECRETS+=",REDIS_URL=redis-url-pre:latest"
SECRETS+=",SECRET_KEY=secret-key-pre:latest"
SECRETS+=",CLERK_SECRET_KEY=clerk-secret-pre:latest"
SECRETS+=",STRIPE_SECRET_KEY=stripe-secret-pre:latest"
SECRETS+=",MICROSERVICES_API_KEY=microservices-api-key-pre:latest"

gcloud run services update $SERVICE_NAME \
    --update-secrets="$SECRETS" \
    --region=$REGION \
    --project=$PROJECT_ID

# Add Cloud SQL connection if needed
echo ""
echo "6️⃣ Configuring Cloud SQL connection..."
INSTANCE_NAME=$(gcloud sql instances list --project=$PROJECT_ID --format="value(name)" | head -1)
if [ ! -z "$INSTANCE_NAME" ]; then
    CONNECTION_NAME="${PROJECT_ID}:${REGION}:${INSTANCE_NAME}"
    echo "Adding Cloud SQL connection: $CONNECTION_NAME"
    gcloud run services update $SERVICE_NAME \
        --add-cloudsql-instances=$CONNECTION_NAME \
        --region=$REGION \
        --project=$PROJECT_ID
fi

# Wait for deployment
echo ""
echo "⏳ Waiting for deployment to complete..."
sleep 30

# Test the service
echo ""
echo "7️⃣ Testing the service..."
BACKEND_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --project=$PROJECT_ID --format='value(status.url)')
echo "Backend URL: $BACKEND_URL"

response=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" || echo "failed")
if [ "$response" = "200" ]; then
    echo "✅ Health check passed!"
    curl -s "$BACKEND_URL/health" | jq .
else
    echo "⚠️  Health check returned: $response"
    echo "Checking recent logs..."
    gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME AND severity>=ERROR" \
        --project=$PROJECT_ID \
        --limit=10 \
        --format="table(timestamp,textPayload)" | head -20
fi

echo ""
echo "✅ Backend deployment complete!"
echo ""
echo "Summary:"
echo "- Service: $SERVICE_NAME"
echo "- URL: $BACKEND_URL"
echo "- Region: $REGION"
echo "- Memory: 8Gi"
echo "- CPU: 4 cores"
echo "- Min instances: 1"
echo ""
echo "Next steps:"
echo "1. Update nginx proxy to route to: $BACKEND_URL"
echo "2. Test API endpoints through the domain"
echo "3. Monitor logs: gcloud logging read \"resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME\" --project=$PROJECT_ID"