#!/bin/bash
# Setup Google Cloud Secrets with your existing configuration

set -e

PROJECT_ID="nexusdocs360-pre"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔐 Setting up Google Cloud Secrets${NC}"

# Set project
gcloud config set project ${PROJECT_ID}

# Create secrets using environment variables
# Please set these environment variables before running this script:
# export CLERK_SECRET_KEY="your-clerk-secret"
# export STRIPE_SECRET_KEY="your-stripe-secret"
# export STRIPE_WEBHOOK_SECRET="your-webhook-secret"
# export POSTGRES_PASSWORD="your-db-password"
# export MICROSERVICES_API_KEY="your-api-key"
# export MAIL_PASSWORD="your-mail-password"

echo -e "${YELLOW}Creating Clerk secret...${NC}"
if [ -n "$CLERK_SECRET_KEY" ]; then
    echo "$CLERK_SECRET_KEY" | gcloud secrets create clerk-secret-key --data-file=- || echo "Secret already exists"
else
    echo -e "${RED}⚠️  CLERK_SECRET_KEY environment variable not set${NC}"
fi

echo -e "${YELLOW}Creating Stripe secret...${NC}"
if [ -n "$STRIPE_SECRET_KEY" ]; then
    echo "$STRIPE_SECRET_KEY" | gcloud secrets create stripe-secret-key --data-file=- || echo "Secret already exists"
else
    echo -e "${RED}⚠️  STRIPE_SECRET_KEY environment variable not set${NC}"
fi

echo -e "${YELLOW}Creating Stripe webhook secret...${NC}"
if [ -n "$STRIPE_WEBHOOK_SECRET" ]; then
    echo "$STRIPE_WEBHOOK_SECRET" | gcloud secrets create stripe-webhook-secret --data-file=- || echo "Secret already exists"
else
    echo -e "${RED}⚠️  STRIPE_WEBHOOK_SECRET environment variable not set${NC}"
fi

echo -e "${YELLOW}Creating database password...${NC}"
if [ -n "$POSTGRES_PASSWORD" ]; then
    echo "$POSTGRES_PASSWORD" | gcloud secrets create postgres-password --data-file=- || echo "Secret already exists"
else
    echo -e "${RED}⚠️  POSTGRES_PASSWORD environment variable not set${NC}"
fi

echo -e "${YELLOW}Creating microservices API key...${NC}"
if [ -n "$MICROSERVICES_API_KEY" ]; then
    echo "$MICROSERVICES_API_KEY" | gcloud secrets create microservices-api-key --data-file=- || echo "Secret already exists"
else
    echo -e "${RED}⚠️  MICROSERVICES_API_KEY environment variable not set${NC}"
fi

echo -e "${YELLOW}Creating mail password...${NC}"
if [ -n "$MAIL_PASSWORD" ]; then
    echo "$MAIL_PASSWORD" | gcloud secrets create mail-password --data-file=- || echo "Secret already exists"
else
    echo -e "${RED}⚠️  MAIL_PASSWORD environment variable not set${NC}"
fi

echo -e "${YELLOW}Creating GCS credentials...${NC}"
# Look for credentials file in common locations
CREDS_FILE=""
if [ -f "backend/credentials/nexusdocs360-pre-04252dae0146.json" ]; then
    CREDS_FILE="backend/credentials/nexusdocs360-pre-04252dae0146.json"
elif [ -f "credentials/nexusdocs360-pre-04252dae0146.json" ]; then
    CREDS_FILE="credentials/nexusdocs360-pre-04252dae0146.json"
elif [ -f "nexusdocs360-pre-04252dae0146.json" ]; then
    CREDS_FILE="nexusdocs360-pre-04252dae0146.json"
fi

if [ -n "$CREDS_FILE" ]; then
    gcloud secrets create gcs-credentials --data-file="$CREDS_FILE" || echo "Secret already exists"
    echo -e "${GREEN}✅ GCS credentials uploaded from: $CREDS_FILE${NC}"
else
    echo -e "${RED}⚠️  GCS credentials file not found. Please place nexusdocs360-pre-04252dae0146.json in one of these locations:${NC}"
    echo -e "${YELLOW}  - backend/credentials/nexusdocs360-pre-04252dae0146.json${NC}"
    echo -e "${YELLOW}  - credentials/nexusdocs360-pre-04252dae0146.json${NC}"
    echo -e "${YELLOW}  - nexusdocs360-pre-04252dae0146.json${NC}"
    echo -e "${YELLOW}Then create the secret manually with:${NC}"
    echo "gcloud secrets create gcs-credentials --data-file=path/to/nexusdocs360-pre-04252dae0146.json"
fi

echo -e "${GREEN}✅ Secrets setup completed!${NC}"
echo -e "${YELLOW}📋 Created secrets:${NC}"
gcloud secrets list --filter="name~clerk-secret-key OR name~stripe-secret-key OR name~postgres-password OR name~microservices-api-key OR name~mail-password OR name~gcs-credentials"