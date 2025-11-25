#!/bin/bash
# Manual deployment script for backend service

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
GAR_LOCATION="europe-west1-docker.pkg.dev"
REPOSITORY="nexusdocs360-pre"
SERVICE_NAME="nexus-backend-pre"

echo "🚀 Manual Backend Deployment to PRE"
echo "===================================="
echo ""

# Set project
gcloud config set project $PROJECT_ID

# Configure Docker
echo "🔧 Configuring Docker..."
gcloud auth configure-docker $GAR_LOCATION

# Build image
echo "🏗️  Building Docker image..."
cd backend
docker build -t $GAR_LOCATION/$PROJECT_ID/$REPOSITORY/backend:manual-fix \
  -f Dockerfile.cloud-run \
  .

# Push image
echo "📤 Pushing image to Artifact Registry..."
docker push $GAR_LOCATION/$PROJECT_ID/$REPOSITORY/backend:manual-fix

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $GAR_LOCATION/$PROJECT_ID/$REPOSITORY/backend:manual-fix \
  --region $REGION \
  --platform managed \
  --port 8000 \
  --allow-unauthenticated \
  --vpc-connector nexus-connector-pre \
  --vpc-egress private-ranges-only \
  --service-account nexus-cloud-run-pre@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars "ENVIRONMENT=pre" \
  --set-secrets "DATABASE_URL=database-url-pre:latest,ASYNC_DATABASE_URL=async-database-url-pre:latest,REDIS_URL=redis-url-pre:latest,SECRET_KEY=secret-key-pre:latest,CLERK_SECRET_KEY=clerk-secret-pre:latest,STRIPE_SECRET_KEY=stripe-secret-pre:latest,SIGNATURE_ENCRYPTION_KEY=signature-encryption-key-pre:latest,MICROSERVICES_API_KEY=microservices-api-key-pre:latest" \
  --min-instances 1 \
  --max-instances 3 \
  --memory 1Gi \
  --cpu 1

echo ""
echo "✅ Deployment complete!"
