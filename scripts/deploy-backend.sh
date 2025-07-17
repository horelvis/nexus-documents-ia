#!/bin/bash
# Deploy Backend to Cloud Run

set -e

# Configuration - Updated with your current setup
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
SERVICE_NAME="nexus-backend"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
CLOUD_SQL_CONNECTION_NAME="nexusdocs360-pre:europe-west1:nexusdocuments360db"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying Backend to Cloud Run${NC}"

# Check if we're in the right directory
if [ ! -f "backend/requirements.txt" ]; then
    echo -e "${RED}❌ Error: Must be run from project root directory${NC}"
    exit 1
fi

# Build and push Docker image
echo -e "${YELLOW}📦 Building Docker image...${NC}"
cd backend
docker build -f Dockerfile.prod -t ${IMAGE_NAME}:latest .

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
    --memory 1Gi \
    --cpu 2 \
    --concurrency 100 \
    --max-instances 20 \
    --min-instances 1 \
    --timeout 300 \
    --port 8000 \
    --add-cloudsql-instances ${CLOUD_SQL_CONNECTION_NAME} \
    --set-env-vars "DEBUG=false,TESTING=false,ALLOW_ALL_CORS=false,GCS_PROJECT_ID=nexusdocs360-pre,GCS_BUCKET_NAME=nexus-docs-eu,POSTGRES_USER=your_user,POSTGRES_DB=nexusdocuments360db,MAIL_USERNAME=hcastillo.mendoza@gmail.es,MAIL_FROM=hcastillo.mendoza@gmail.es" \
    --set-secrets "CLERK_SECRET_KEY=clerk-secret-key:latest,STRIPE_SECRET_KEY=stripe-secret-key:latest,POSTGRES_PASSWORD=postgres-password:latest,MICROSERVICES_API_KEY=microservices-api-key:latest,MAIL_PASSWORD=mail-password:latest" \
    --service-account nexus-backend@${PROJECT_ID}.iam.gserviceaccount.com

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --platform managed \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --format 'value(status.url)')

echo -e "${GREEN}✅ Backend deployed successfully!${NC}"
echo -e "${GREEN}🌐 Service URL: ${SERVICE_URL}${NC}"

cd ..