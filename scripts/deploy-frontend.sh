#!/bin/bash
# Deploy Frontend to Cloud Run

set -e

# Configuration - Updated with your current setup
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-frontend"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying Frontend to Cloud Run${NC}"

# Check if we're in the right directory
if [ ! -f "frontend/package.json" ]; then
    echo -e "${RED}❌ Error: Must be run from project root directory${NC}"
    exit 1
fi

# Build and push Docker image
echo -e "${YELLOW}📦 Building Docker image...${NC}"
cd frontend
# Get backend URL if not provided
if [ -z "$NEXT_PUBLIC_API_BASE_URL" ]; then
    NEXT_PUBLIC_API_BASE_URL=$(gcloud run services describe nexus-backend \
        --platform managed \
        --region ${REGION} \
        --project ${PROJECT_ID} \
        --format 'value(status.url)' 2>/dev/null || echo "https://nexus-backend-HASH-uc.a.run.app")
fi

docker build -f Dockerfile.prod -t ${IMAGE_NAME}:latest \
    --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_test_ZGVlcC1yYWJiaXQtMjkuY2xlcmsuYWNjb3VudHMuZGV2JA" \
    --build-arg NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL}" \
    --build-arg NEXT_PUBLIC_FRONTEND_URL="https://pre.nexusdocs360.app" \
    --build-arg NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY="pk_test_51RitIlR8hZSzPrz7s9giSrKIVQOQrHkxnlDkpRvxFwlJwAayDMsbqlkoweIq164iInWmYsYGaRZ0Tkn7oTKW3d7c00bl16u2XR" \
    .

echo -e "${YELLOW}📤 Pushing image to Container Registry...${NC}"
docker push ${IMAGE_NAME}:latest

# Deploy to Cloud Run
echo -e "${YELLOW}🚚 Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME}:latest \
    --platform managed \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --concurrency 100 \
    --max-instances 10 \
    --min-instances 0 \
    --timeout 300 \
    --set-env-vars "NODE_ENV=production,NEXT_TELEMETRY_DISABLED=1" \
    --port 3000

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --platform managed \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --format 'value(status.url)')

echo -e "${GREEN}✅ Frontend deployed successfully!${NC}"
echo -e "${GREEN}🌐 Service URL: ${SERVICE_URL}${NC}"

cd ..