#!/bin/bash
# Validation script for PRE environment
# Checks all services and configurations are working correctly

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ZONE="europe-west1-b"
DOMAIN="nexusdocs360.com"

echo "🔍 Validating PRE Environment..."
echo "================================"

# Set project
gcloud config set project $PROJECT_ID 2>/dev/null

# Track failures
FAILED=0
WARNINGS=0

# Function to check status
check() {
    local name=$1
    local command=$2
    echo -n "Checking $name... "
    if eval $command > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
        return 1
    fi
}

# Function to warn
warn() {
    local name=$1
    local command=$2
    echo -n "Checking $name... "
    if eval $command > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠ WARNING${NC}"
        ((WARNINGS++))
        return 1
    fi
}

echo -e "\n1️⃣ ${YELLOW}Infrastructure Validation${NC}"
echo "----------------------------"

# Check VPC
check "VPC Network" "gcloud compute networks describe nexus-vpc-pre --format='value(name)'"
check "Subnet" "gcloud compute networks subnets describe nexus-subnet-pre --region=$REGION --format='value(name)'"
check "Cloud NAT" "gcloud compute routers nats describe nexus-nat-pre --router=nexus-router-pre --region=$REGION --format='value(name)'"
check "VPC Connector" "gcloud compute networks vpc-access connectors describe nexus-connector-pre --region=$REGION --format='value(name)'"

echo -e "\n2️⃣ ${YELLOW}Database Services${NC}"
echo "-------------------"

# Check Cloud SQL
check "Cloud SQL Instance" "gcloud sql instances describe nexus-db-pre --format='value(state)' | grep -q RUNNABLE"
DB_IP=$(gcloud sql instances describe nexus-db-pre --format="value(ipAddresses[0].ipAddress)" 2>/dev/null || echo "")
if [ -n "$DB_IP" ]; then
    echo -e "   Cloud SQL IP: ${GREEN}$DB_IP${NC}"
else
    echo -e "   Cloud SQL IP: ${RED}Not found${NC}"
    ((FAILED++))
fi

# Check Redis
check "Redis Instance" "gcloud redis instances describe nexus-redis-pre --region=$REGION --format='value(state)' | grep -q READY"
REDIS_IP=$(gcloud redis instances describe nexus-redis-pre --region=$REGION --format="value(host)" 2>/dev/null || echo "")
if [ -n "$REDIS_IP" ]; then
    echo -e "   Redis IP: ${GREEN}$REDIS_IP${NC}"
else
    echo -e "   Redis IP: ${RED}Not found${NC}"
    ((FAILED++))
fi

echo -e "\n3️⃣ ${YELLOW}Compute Resources${NC}"
echo "--------------------"

# Check VMs
check "Qdrant VM" "gcloud compute instances describe qdrant-pre --zone=$ZONE --format='value(status)' | grep -q RUNNING"
check "Nginx Proxy VM" "gcloud compute instances describe nginx-proxy-pre --zone=$ZONE --format='value(status)' | grep -q RUNNING"

# Get Nginx IP
NGINX_IP=$(gcloud compute addresses describe nexus-nginx-ip-pre --region=$REGION --format="value(address)" 2>/dev/null || echo "")
if [ -n "$NGINX_IP" ]; then
    echo -e "   Nginx IP: ${GREEN}$NGINX_IP${NC}"
else
    echo -e "   Nginx IP: ${RED}Not found${NC}"
    ((FAILED++))
fi

echo -e "\n4️⃣ ${YELLOW}Cloud Run Services${NC}"
echo "---------------------"

# Check Cloud Run services
for service in api frontend langchain langroid storage; do
    if gcloud run services describe nexus-${service}-pre --region=$REGION --format="value(status.url)" > /dev/null 2>&1; then
        URL=$(gcloud run services describe nexus-${service}-pre --region=$REGION --format="value(status.url)")
        echo -e "   nexus-${service}-pre: ${GREEN}✓ Running${NC}"
        echo -e "      URL: $URL"
    else
        echo -e "   nexus-${service}-pre: ${RED}✗ Not found${NC}"
        ((FAILED++))
    fi
done

echo -e "\n5️⃣ ${YELLOW}Storage Buckets${NC}"
echo "-----------------"

# Check buckets
for bucket in nexusdocs360-pre-docs-eu nexusdocs360-pre-backups-eu nexusdocs360-pre-scripts; do
    check "Bucket $bucket" "gsutil ls -b gs://$bucket"
done

echo -e "\n6️⃣ ${YELLOW}Secrets Configuration${NC}"
echo "-----------------------"

# Check critical secrets
SECRETS=(
    "db-user-pre"
    "db-pass-pre"
    "db-host-pre"
    "database-url-pre"
    "redis-url-pre"
    "openai-api-key-pre"
    "clerk-secret-pre"
    "microservices-api-key-pre"
)

for secret in "${SECRETS[@]}"; do
    warn "Secret $secret" "gcloud secrets describe $secret --format='value(name)'"
done

echo -e "\n7️⃣ ${YELLOW}DNS Configuration${NC}"
echo "-------------------"

# Check DNS resolution
echo "Checking DNS records (may fail if not propagated yet)..."
for subdomain in pre pre-app pre-api; do
    IP=$(nslookup ${subdomain}.${DOMAIN} 8.8.8.8 2>/dev/null | grep -A1 "Name:" | grep "Address:" | awk '{print $2}' | grep -v "#" | head -1)
    if [ -n "$IP" ]; then
        if [ "$IP" = "$NGINX_IP" ]; then
            echo -e "   ${subdomain}.${DOMAIN}: ${GREEN}✓ Resolves to $IP${NC}"
        else
            echo -e "   ${subdomain}.${DOMAIN}: ${YELLOW}⚠ Resolves to $IP (expected $NGINX_IP)${NC}"
            ((WARNINGS++))
        fi
    else
        echo -e "   ${subdomain}.${DOMAIN}: ${YELLOW}⚠ Not resolving yet${NC}"
        ((WARNINGS++))
    fi
done

echo -e "\n8️⃣ ${YELLOW}HTTPS Endpoints${NC}"
echo "------------------"

# Check HTTPS endpoints
echo "Checking HTTPS endpoints..."
for endpoint in "pre-app.${DOMAIN}" "pre-api.${DOMAIN}/health"; do
    response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "https://${endpoint}" 2>/dev/null || echo "000")
    if [ "$response" = "200" ]; then
        echo -e "   https://${endpoint}: ${GREEN}✓ 200 OK${NC}"
    elif [ "$response" = "000" ]; then
        echo -e "   https://${endpoint}: ${YELLOW}⚠ Connection timeout${NC}"
        ((WARNINGS++))
    else
        echo -e "   https://${endpoint}: ${RED}✗ HTTP $response${NC}"
        ((FAILED++))
    fi
done

echo -e "\n9️⃣ ${YELLOW}Service Health Checks${NC}"
echo "-----------------------"

# Internal health checks via Cloud Run URLs
echo "Checking internal service health..."
for service in api frontend; do
    URL=$(gcloud run services describe nexus-${service}-pre --region=$REGION --format="value(status.url)" 2>/dev/null)
    if [ -n "$URL" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${URL}/health" 2>/dev/null || echo "000")
        if [ "$response" = "200" ]; then
            echo -e "   ${service} health: ${GREEN}✓ OK${NC}"
        else
            echo -e "   ${service} health: ${RED}✗ HTTP $response${NC}"
            ((FAILED++))
        fi
    fi
done

echo -e "\n🔟 ${YELLOW}Monitoring & Logs${NC}"
echo "-------------------"

# Check monitoring
check "Monitoring API" "gcloud services list --enabled --filter='name:monitoring.googleapis.com' --format='value(name)'"
check "Logging API" "gcloud services list --enabled --filter='name:logging.googleapis.com' --format='value(name)'"

# Check for recent errors
echo -n "Checking for recent errors... "
ERROR_COUNT=$(gcloud logging read "severity>=ERROR AND timestamp>=\"$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%S')\"" --limit=10 --format=json 2>/dev/null | jq length)
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ No errors in last hour${NC}"
else
    echo -e "${YELLOW}⚠ Found $ERROR_COUNT errors in last hour${NC}"
    ((WARNINGS++))
fi

echo -e "\n================================"
echo -e "📊 ${YELLOW}Validation Summary${NC}"
echo "================================"

if [ $FAILED -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed!${NC}"
    echo -e "\n🎉 PRE environment is fully operational!"
    exit 0
elif [ $FAILED -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Validation completed with $WARNINGS warnings${NC}"
    echo -e "\nPRE environment is operational but check warnings above."
    exit 0
else
    echo -e "${RED}❌ Validation failed with $FAILED errors and $WARNINGS warnings${NC}"
    echo -e "\nPlease fix the errors above before proceeding."
    exit 1
fi