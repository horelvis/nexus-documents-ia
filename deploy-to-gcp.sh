#!/bin/bash
# One-click deployment script for NexusDocs360 to GCP

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -f "$SCRIPT_DIR/deployment/gcp/.env" ]; then
    source "$SCRIPT_DIR/deployment/gcp/load-env.sh" "$SCRIPT_DIR/deployment/gcp/.env"
fi

# Default values from environment or arguments
PROJECT_ID="${1:-${GCP_PROJECT_ID:-nexus-document-prod}}"
REGION="${2:-${GCP_REGION:-europe-west1}}"
ZONE="${3:-${GCP_ZONE:-europe-west1-b}}"
DOMAIN="${DOMAIN:-nexusdocs.com}"

echo -e "${GREEN}🚀 NexusDocs360 - GCP Deployment${NC}"
echo -e "${GREEN}===========================================${NC}"
echo ""
echo -e "Project ID: ${YELLOW}$PROJECT_ID${NC}"
echo -e "Region: ${YELLOW}$REGION${NC}"
echo -e "Zone: ${YELLOW}$ZONE${NC}"
echo -e "Domain: ${YELLOW}$DOMAIN${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Check if project exists, create if not
echo -e "${YELLOW}📋 Setting up GCP project...${NC}"
if ! gcloud projects describe $PROJECT_ID &>/dev/null; then
    echo -e "${YELLOW}Creating project $PROJECT_ID...${NC}"
    gcloud projects create $PROJECT_ID --name="NexusDocs360"
    echo -e "${GREEN}✓ Project created${NC}"
fi
gcloud config set project $PROJECT_ID

# Step 1: Setup secrets
echo -e "${YELLOW}🔐 Step 1/4: Setting up secrets...${NC}"
cd deployment/gcp
./setup-secrets.sh $PROJECT_ID $REGION
cd ../..

echo -e "${RED}⚠️  IMPORTANT: Update these secrets before continuing:${NC}"
echo "  - clerk-secret"
echo "  - clerk-jwt-key" 
echo "  - clerk-publishable-key"
echo "  - stripe-secret"
echo "  - stripe-webhook-secret"
echo "  - sendgrid-api-key"
echo ""
read -p "Have you updated all secrets? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}❌ Please update secrets and run again.${NC}"
    exit 1
fi

# Step 2: Deploy infrastructure
echo -e "${YELLOW}🏗️ Step 2/4: Deploying infrastructure...${NC}"
cd deployment/gcp
./deploy-infrastructure.sh $PROJECT_ID $REGION $ZONE
cd ../..

# Step 3: Build and deploy applications
echo -e "${YELLOW}🐳 Step 3/4: Building and deploying applications...${NC}"
gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT_ID

# Step 4: Get deployment info
echo -e "${YELLOW}📊 Step 4/4: Getting deployment information...${NC}"
FRONTEND_IP=$(gcloud compute addresses describe nexus-frontend-ip --global --format="value(address)" --project=$PROJECT_ID)
API_IP=$(gcloud compute addresses describe nexus-api-ip --global --format="value(address)" --project=$PROJECT_ID)
FRONTEND_URL=$(gcloud run services describe nexus-frontend --region=$REGION --format="value(status.url)" --project=$PROJECT_ID)
API_URL=$(gcloud run services describe nexus-api --region=$REGION --format="value(status.url)" --project=$PROJECT_ID)

echo ""
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}=====================${NC}"
echo ""
echo -e "${YELLOW}📍 DNS Configuration:${NC}"
echo -e "  Frontend: app.nexusdocs.com → ${GREEN}$FRONTEND_IP${NC}"
echo -e "  API: api.nexusdocs.com → ${GREEN}$API_IP${NC}"
echo ""
echo -e "${YELLOW}🔗 Temporary URLs (before DNS):${NC}"
echo -e "  Frontend: ${GREEN}$FRONTEND_URL${NC}"
echo -e "  API: ${GREEN}$API_URL${NC}"
echo ""
echo -e "${YELLOW}📊 Monitoring:${NC}"
echo -e "  Cloud Console: ${GREEN}https://console.cloud.google.com/home/dashboard?project=$PROJECT_ID${NC}"
echo -e "  Cloud Run: ${GREEN}https://console.cloud.google.com/run?project=$PROJECT_ID${NC}"
echo -e "  Logs: ${GREEN}https://console.cloud.google.com/logs?project=$PROJECT_ID${NC}"
echo ""
echo -e "${YELLOW}🚀 Next Steps:${NC}"
echo "  1. Configure DNS records as shown above"
echo "  2. Wait for SSL certificates (15-30 min after DNS)"
echo "  3. Test application at https://app.nexusdocs.com"
echo "  4. Monitor logs and metrics"
echo ""