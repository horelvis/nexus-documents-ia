#!/bin/bash
# Validate complete deployment
# This script checks all components of the deployment

set -e

echo "🔍 Validating Deployment"
echo "======================="
echo ""

# Configuration
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
DOMAIN="nexusdocs360.app"
FRONTEND_URL="https://pre.${DOMAIN}"
API_URL="https://pre-api.${DOMAIN}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check status
check_status() {
    local name=$1
    local status=$2
    if [ "$status" = "ok" ]; then
        echo -e "${GREEN}✅ $name${NC}"
    else
        echo -e "${RED}❌ $name${NC}"
    fi
}

echo "1️⃣ Checking Google Cloud Services..."
echo ""

# Check Cloud Run backend
echo -n "Cloud Run Backend: "
BACKEND_STATUS=$(gcloud run services describe nexus-backend-pre \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(status.conditions[0].status)" 2>/dev/null || echo "false")
if [ "$BACKEND_STATUS" = "True" ]; then
    check_status "Running" "ok"
    BACKEND_URL=$(gcloud run services describe nexus-backend-pre \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(status.url)")
    echo "   URL: $BACKEND_URL"
else
    check_status "Not running" "failed"
fi

# Check Cloud SQL
echo -n "Cloud SQL: "
SQL_INSTANCES=$(gcloud sql instances list --project=$PROJECT_ID --format="value(name)" | wc -l)
if [ "$SQL_INSTANCES" -gt 0 ]; then
    check_status "Available ($SQL_INSTANCES instance(s))" "ok"
else
    check_status "No instances found" "failed"
fi

# Check secrets
echo -n "Secrets: "
SECRET_COUNT=$(gcloud secrets list --project=$PROJECT_ID --filter="name:pre" --format="value(name)" | wc -l)
check_status "$SECRET_COUNT secrets configured" "ok"

echo ""
echo "2️⃣ Checking Direct Service Endpoints..."
echo ""

# Test backend health directly
echo -n "Backend Health (direct): "
if [ ! -z "$BACKEND_URL" ]; then
    response=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" || echo "failed")
    if [ "$response" = "200" ]; then
        check_status "HTTP $response" "ok"
    else
        check_status "HTTP $response" "failed"
    fi
else
    check_status "No backend URL" "failed"
fi

echo ""
echo "3️⃣ Checking Domain Endpoints..."
echo ""

# Test frontend
echo -n "Frontend ($FRONTEND_URL): "
response=$(curl -s -o /dev/null -w "%{http_code}" -L "$FRONTEND_URL" || echo "failed")
if [ "$response" = "200" ]; then
    check_status "HTTP $response" "ok"
else
    check_status "HTTP $response" "failed"
fi

# Test API
echo -n "API ($API_URL): "
response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" || echo "failed")
if [ "$response" = "200" ]; then
    check_status "HTTP $response" "ok"
else
    check_status "HTTP $response" "failed"
fi

# Test API CORS
echo -n "API CORS: "
cors_header=$(curl -s -I -X OPTIONS "$API_URL/" \
    -H "Origin: $FRONTEND_URL" \
    -H "Access-Control-Request-Method: GET" | grep -i "access-control-allow-origin" || echo "")
if [ ! -z "$cors_header" ]; then
    check_status "Headers present" "ok"
else
    check_status "Headers missing" "failed"
fi

echo ""
echo "4️⃣ Checking SSL Certificates..."
echo ""

# Check SSL for frontend
echo -n "Frontend SSL: "
if curl -s -I "$FRONTEND_URL" 2>&1 | grep -q "SSL certificate problem"; then
    check_status "Invalid certificate" "failed"
else
    check_status "Valid" "ok"
fi

# Check SSL for API
echo -n "API SSL: "
if curl -s -I "$API_URL" 2>&1 | grep -q "SSL certificate problem"; then
    check_status "Invalid certificate" "failed"
else
    check_status "Valid" "ok"
fi

echo ""
echo "5️⃣ Checking Recent Errors..."
echo ""

# Check for recent backend errors
ERROR_COUNT=$(gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=nexus-backend-pre AND severity>=ERROR AND timestamp>=\"$(date -u -v-10M '+%Y-%m-%dT%H:%M:%S')Z\"" \
    --project=$PROJECT_ID \
    --limit=10 \
    --format="value(textPayload)" 2>/dev/null | wc -l || echo "0")

if [ "$ERROR_COUNT" -eq "0" ]; then
    check_status "No recent errors" "ok"
else
    check_status "$ERROR_COUNT errors in last 10 minutes" "failed"
fi

echo ""
echo "6️⃣ Summary"
echo "========="
echo ""
echo "Frontend URL: $FRONTEND_URL"
echo "API URL: $API_URL"
echo "Backend Direct: ${BACKEND_URL:-Not found}"
echo ""
echo "Quick commands:"
echo "- View backend logs: gcloud logging read \"resource.type=cloud_run_revision AND resource.labels.service_name=nexus-backend-pre\" --project=$PROJECT_ID --limit=20"
echo "- SSH to nginx: gcloud compute ssh nginx-proxy-pre --zone=europe-west1-b --project=$PROJECT_ID"
echo "- Update backend: gcloud run deploy nexus-backend-pre --region=$REGION --project=$PROJECT_ID"
echo ""

# Final status
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✅ Deployment is healthy!${NC}"
else
    echo -e "${YELLOW}⚠️  Some components need attention${NC}"
fi