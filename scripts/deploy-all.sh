#!/bin/bash
# Deploy both Frontend and Backend to Cloud Run

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying NexusDocs360 to Cloud Run${NC}"

# Check if we're in the right directory
if [ ! -f "package.json" ] || [ ! -f "backend/requirements.txt" ]; then
    echo -e "${RED}❌ Error: Must be run from project root directory${NC}"
    exit 1
fi

# Deploy backend first
echo -e "${YELLOW}📚 Deploying Backend...${NC}"
./scripts/deploy-backend.sh

# Wait a bit for backend to be ready
echo -e "${YELLOW}⏳ Waiting for backend to be ready...${NC}"
sleep 10

# Deploy frontend
echo -e "${YELLOW}🎨 Deploying Frontend...${NC}"
./scripts/deploy-frontend.sh

echo -e "${GREEN}✅ Complete deployment finished!${NC}"
echo -e "${GREEN}🎉 NexusDocs360 is now live on Cloud Run${NC}"