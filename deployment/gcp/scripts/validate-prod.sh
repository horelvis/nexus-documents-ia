#!/bin/bash
# Validation script for PRODUCTION environment
# Comprehensive checks for all services, security, and performance

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="nexusdocs360-prod"
REGION="europe-west1"
ZONE="europe-west1-b"
DOMAIN="nexusdocs360.com"

echo "🔍 Validating PRODUCTION Environment..."
echo "======================================"

# Set project
gcloud config set project $PROJECT_ID 2>/dev/null

# Track failures
FAILED=0
WARNINGS=0
CRITICAL=0

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

# Function to check critical
critical_check() {
    local name=$1
    local command=$2
    echo -n "🚨 Checking $name... "
    if eval $command > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ CRITICAL FAILURE${NC}"
        ((CRITICAL++))
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

# Check VPC and networking
check "VPC Network" "gcloud compute networks describe nexus-vpc-prod --format='value(name)'"
check "Primary Subnet" "gcloud compute networks subnets describe nexus-subnet-prod-primary --region=$REGION --format='value(name)'"
check "Secondary Subnet" "gcloud compute networks subnets describe nexus-subnet-prod-secondary --region=$REGION --format='value(name)'"
check "Cloud NAT" "gcloud compute routers nats describe nexus-nat-prod --router=nexus-router-prod --region=$REGION --format='value(name)'"
check "VPC Connector" "gcloud compute networks vpc-access connectors describe nexus-connector-prod --region=$REGION --format='value(name)'"

# Check NAT IPs
NAT_IPS=$(gcloud compute addresses list --filter="name:(nexus-nat-ip-1 OR nexus-nat-ip-2)" --format="value(address)" 2>/dev/null)
if [ -n "$NAT_IPS" ]; then
    echo -e "   NAT IPs: ${GREEN}$(echo $NAT_IPS | tr '\n' ', ')${NC}"
else
    echo -e "   NAT IPs: ${RED}Not found${NC}"
    ((FAILED++))
fi

echo -e "\n2️⃣ ${YELLOW}Database Services (HA)${NC}"
echo "------------------------"

# Check Cloud SQL with HA
critical_check "Cloud SQL Primary" "gcloud sql instances describe nexus-db-prod --format='value(state)' | grep -q RUNNABLE"
critical_check "Cloud SQL HA" "gcloud sql instances describe nexus-db-prod --format='value(settings.availabilityType)' | grep -q REGIONAL"
check "Cloud SQL Replica" "gcloud sql instances describe nexus-db-prod-replica --format='value(state)' | grep -q RUNNABLE"

# Check backup configuration
BACKUP_ENABLED=$(gcloud sql instances describe nexus-db-prod --format="value(settings.backupConfiguration.enabled)" 2>/dev/null)
if [ "$BACKUP_ENABLED" = "True" ]; then
    echo -e "   Automated Backups: ${GREEN}✓ Enabled${NC}"
else
    echo -e "   Automated Backups: ${RED}✗ Disabled${NC}"
    ((CRITICAL++))
fi

# Check Redis with HA
critical_check "Redis Instance" "gcloud redis instances describe nexus-redis-prod --region=$REGION --format='value(state)' | grep -q READY"
critical_check "Redis HA" "gcloud redis instances describe nexus-redis-prod --region=$REGION --format='value(tier)' | grep -q STANDARD_HA"

echo -e "\n3️⃣ ${YELLOW}Compute Resources (Cluster)${NC}"
echo "------------------------------"

# Check Qdrant cluster
check "Qdrant Instance Group" "gcloud compute instance-groups managed describe qdrant-prod-group --zone=$ZONE --format='value(name)'"
QDRANT_SIZE=$(gcloud compute instance-groups managed describe qdrant-prod-group --zone=$ZONE --format="value(targetSize)" 2>/dev/null || echo "0")
if [ "$QDRANT_SIZE" -ge 3 ]; then
    echo -e "   Qdrant Cluster Size: ${GREEN}$QDRANT_SIZE nodes${NC}"
else
    echo -e "   Qdrant Cluster Size: ${YELLOW}$QDRANT_SIZE nodes (recommended: 3+)${NC}"
    ((WARNINGS++))
fi

# Check Nginx load balancer
check "Nginx Instance Group" "gcloud compute instance-groups managed describe nginx-prod-group --zone=$ZONE --format='value(name)'"
check "Backend Service" "gcloud compute backend-services describe nginx-backend-prod --global --format='value(name)'"
check "Health Check" "gcloud compute health-checks describe nginx-prod-health --format='value(name)'"

# Get Load Balancer IP
LB_IP=$(gcloud compute addresses describe nexus-lb-ip-prod --global --format="value(address)" 2>/dev/null || echo "")
if [ -n "$LB_IP" ]; then
    echo -e "   Load Balancer IP: ${GREEN}$LB_IP${NC}"
else
    echo -e "   Load Balancer IP: ${RED}Not found${NC}"
    ((CRITICAL++))
fi

echo -e "\n4️⃣ ${YELLOW}Cloud Run Services (Production Scale)${NC}"
echo "---------------------------------------"

# Check Cloud Run services with production config
for service in api frontend langchain langroid storage; do
    if gcloud run services describe nexus-${service}-prod --region=$REGION > /dev/null 2>&1; then
        # Get service details
        MIN_INSTANCES=$(gcloud run services describe nexus-${service}-prod --region=$REGION --format="value(spec.template.metadata.annotations.'autoscaling.knative.dev/minScale')" 2>/dev/null || echo "0")
        MAX_INSTANCES=$(gcloud run services describe nexus-${service}-prod --region=$REGION --format="value(spec.template.metadata.annotations.'autoscaling.knative.dev/maxScale')" 2>/dev/null || echo "?")
        
        echo -e "   nexus-${service}-prod: ${GREEN}✓ Running${NC}"
        echo -e "      Scaling: min=$MIN_INSTANCES, max=$MAX_INSTANCES"
        
        # Critical services should have min instances > 0
        if [[ "$service" =~ ^(api|frontend)$ ]] && [ "$MIN_INSTANCES" -eq 0 ]; then
            echo -e "      ${YELLOW}⚠ Warning: Critical service with min instances = 0${NC}"
            ((WARNINGS++))
        fi
    else
        echo -e "   nexus-${service}-prod: ${RED}✗ Not found${NC}"
        ((CRITICAL++))
    fi
done

echo -e "\n5️⃣ ${YELLOW}Storage & CDN${NC}"
echo "----------------"

# Check buckets with versioning
for bucket in nexusdocs360-prod-docs-eu nexusdocs360-prod-backups-eu nexusdocs360-prod-static; do
    if gsutil ls -b gs://$bucket > /dev/null 2>&1; then
        VERSIONING=$(gsutil versioning get gs://$bucket 2>/dev/null | grep -q "Enabled" && echo "Enabled" || echo "Disabled")
        echo -e "   Bucket $bucket: ${GREEN}✓ Exists${NC}"
        if [ "$VERSIONING" = "Enabled" ]; then
            echo -e "      Versioning: ${GREEN}✓ Enabled${NC}"
        else
            echo -e "      Versioning: ${YELLOW}⚠ Disabled${NC}"
            ((WARNINGS++))
        fi
    else
        echo -e "   Bucket $bucket: ${RED}✗ Not found${NC}"
        ((FAILED++))
    fi
done

# Check CDN
check "CDN Backend" "gcloud compute backend-buckets describe nexus-cdn-backend-prod --format='value(name)'"

echo -e "\n6️⃣ ${YELLOW}Security Configuration${NC}"
echo "------------------------"

# Check KMS
critical_check "KMS Keyring" "gcloud kms keyrings describe nexus-keyring-prod --location=$REGION --format='value(name)'"
critical_check "KMS Key" "gcloud kms keys describe nexus-key-prod --keyring=nexus-keyring-prod --location=$REGION --format='value(name)'"

# Check critical secrets
echo -e "\n   ${BLUE}Production Secrets:${NC}"
CRITICAL_SECRETS=(
    "database-url-prod"
    "redis-url-prod"
    "openai-api-key-prod"
    "clerk-secret-prod"
    "stripe-secret-prod"
)

for secret in "${CRITICAL_SECRETS[@]}"; do
    critical_check "Secret $secret" "gcloud secrets describe $secret --format='value(name)'"
done

echo -e "\n7️⃣ ${YELLOW}DNS & SSL Configuration${NC}"
echo "-------------------------"

# Check DNS resolution
echo "Checking DNS records..."
for subdomain in "" "www" "app" "api"; do
    if [ -z "$subdomain" ]; then
        check_domain="$DOMAIN"
    else
        check_domain="${subdomain}.${DOMAIN}"
    fi
    
    IP=$(dig +short $check_domain @8.8.8.8 2>/dev/null | grep -E '^[0-9.]+$' | head -1)
    if [ -n "$IP" ]; then
        if [ "$IP" = "$LB_IP" ]; then
            echo -e "   $check_domain: ${GREEN}✓ → $IP${NC}"
        else
            echo -e "   $check_domain: ${YELLOW}⚠ → $IP (expected $LB_IP)${NC}"
            ((WARNINGS++))
        fi
    else
        echo -e "   $check_domain: ${RED}✗ Not resolving${NC}"
        ((CRITICAL++))
    fi
done

# Check SSL certificates
echo -e "\n   ${BLUE}SSL Certificate Status:${NC}"
for subdomain in "" "app" "api"; do
    if [ -z "$subdomain" ]; then
        check_domain="$DOMAIN"
    else
        check_domain="${subdomain}.${DOMAIN}"
    fi
    
    # Check certificate validity
    if timeout 5 openssl s_client -servername $check_domain -connect ${check_domain}:443 </dev/null 2>/dev/null | openssl x509 -noout -dates 2>/dev/null; then
        # Get expiry date
        EXPIRY=$(echo | openssl s_client -servername $check_domain -connect ${check_domain}:443 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
        if [ -n "$EXPIRY" ]; then
            DAYS_LEFT=$(( ($(date -d "$EXPIRY" +%s) - $(date +%s)) / 86400 ))
            if [ $DAYS_LEFT -gt 30 ]; then
                echo -e "   $check_domain SSL: ${GREEN}✓ Valid ($DAYS_LEFT days)${NC}"
            else
                echo -e "   $check_domain SSL: ${YELLOW}⚠ Expires soon ($DAYS_LEFT days)${NC}"
                ((WARNINGS++))
            fi
        fi
    else
        echo -e "   $check_domain SSL: ${RED}✗ Certificate error${NC}"
        ((CRITICAL++))
    fi
done

echo -e "\n8️⃣ ${YELLOW}HTTPS Endpoints & Performance${NC}"
echo "---------------------------------"

# Check HTTPS endpoints with timing
for endpoint in "" "app" "api/health"; do
    if [ "$endpoint" = "" ]; then
        url="https://${DOMAIN}"
    else
        url="https://${endpoint}.${DOMAIN}"
    fi
    
    echo -n "   Testing $url... "
    TIMING=$(curl -o /dev/null -s -w "HTTP:%{http_code} Time:%{time_total}s" --connect-timeout 10 "$url" 2>/dev/null || echo "HTTP:000")
    HTTP_CODE=$(echo $TIMING | grep -oE "HTTP:[0-9]+" | cut -d: -f2)
    TIME_TOTAL=$(echo $TIMING | grep -oE "Time:[0-9.]+" | cut -d: -f2)
    
    if [[ "$HTTP_CODE" =~ ^(200|301|302)$ ]]; then
        if (( $(echo "$TIME_TOTAL < 2.0" | bc -l) )); then
            echo -e "${GREEN}✓ $HTTP_CODE in ${TIME_TOTAL}s${NC}"
        else
            echo -e "${YELLOW}⚠ $HTTP_CODE in ${TIME_TOTAL}s (slow)${NC}"
            ((WARNINGS++))
        fi
    else
        echo -e "${RED}✗ HTTP $HTTP_CODE${NC}"
        ((CRITICAL++))
    fi
done

echo -e "\n9️⃣ ${YELLOW}Security Headers Check${NC}"
echo "------------------------"

# Check security headers
echo "Checking security headers..."
HEADERS=$(curl -sI https://app.${DOMAIN} 2>/dev/null)
SECURITY_HEADERS=(
    "Strict-Transport-Security"
    "X-Frame-Options"
    "X-Content-Type-Options"
    "X-XSS-Protection"
    "Referrer-Policy"
)

for header in "${SECURITY_HEADERS[@]}"; do
    if echo "$HEADERS" | grep -qi "^$header:"; then
        echo -e "   $header: ${GREEN}✓ Present${NC}"
    else
        echo -e "   $header: ${RED}✗ Missing${NC}"
        ((WARNINGS++))
    fi
done

echo -e "\n🔟 ${YELLOW}Monitoring & Alerting${NC}"
echo "-----------------------"

# Check monitoring
critical_check "Monitoring API" "gcloud services list --enabled --filter='name:monitoring.googleapis.com' --format='value(name)'"
critical_check "Logging API" "gcloud services list --enabled --filter='name:logging.googleapis.com' --format='value(name)'"
check "Error Reporting" "gcloud services list --enabled --filter='name:clouderrorreporting.googleapis.com' --format='value(name)'"
check "Cloud Trace" "gcloud services list --enabled --filter='name:cloudtrace.googleapis.com' --format='value(name)'"

# Check alert policies
ALERT_COUNT=$(gcloud alpha monitoring policies list --format="value(name)" 2>/dev/null | wc -l)
if [ $ALERT_COUNT -gt 0 ]; then
    echo -e "   Alert Policies: ${GREEN}✓ $ALERT_COUNT configured${NC}"
else
    echo -e "   Alert Policies: ${RED}✗ None configured${NC}"
    ((CRITICAL++))
fi

# Check for recent errors
echo -n "   Recent errors (1h): "
ERROR_COUNT=$(gcloud logging read "severity>=ERROR AND timestamp>=\"$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%S')\"" --limit=50 --format=json 2>/dev/null | jq length)
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ None${NC}"
elif [ "$ERROR_COUNT" -lt 10 ]; then
    echo -e "${YELLOW}⚠ $ERROR_COUNT errors${NC}"
    ((WARNINGS++))
else
    echo -e "${RED}✗ $ERROR_COUNT errors (high)${NC}"
    ((CRITICAL++))
fi

# Check uptime
echo -e "\n   ${BLUE}Service Uptime (24h):${NC}"
# This would require actual uptime monitoring data
echo "   Note: Configure uptime checks in Cloud Monitoring"

echo -e "\n======================================"
echo -e "📊 ${YELLOW}PRODUCTION Validation Summary${NC}"
echo "======================================"

# Summary with different severity levels
if [ $CRITICAL -eq 0 ] && [ $FAILED -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed perfectly!${NC}"
    echo -e "\n🎉 PRODUCTION environment is fully operational and secure!"
    echo -e "\n${BLUE}Next steps:${NC}"
    echo "- Monitor dashboards: https://console.cloud.google.com/monitoring?project=$PROJECT_ID"
    echo "- Review costs: https://console.cloud.google.com/billing?project=$PROJECT_ID"
    exit 0
elif [ $CRITICAL -eq 0 ] && [ $FAILED -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Validation completed with $WARNINGS warnings${NC}"
    echo -e "\nPRODUCTION is operational. Review warnings for optimization opportunities."
    exit 0
elif [ $CRITICAL -eq 0 ]; then
    echo -e "${RED}❌ Validation found $FAILED errors and $WARNINGS warnings${NC}"
    echo -e "\nPRODUCTION has issues that should be addressed soon."
    exit 1
else
    echo -e "${RED}🚨 CRITICAL: Found $CRITICAL critical issues, $FAILED errors, and $WARNINGS warnings${NC}"
    echo -e "\n⛔ PRODUCTION has critical issues that need immediate attention!"
    echo -e "\n${BLUE}Emergency contacts:${NC}"
    echo "- On-call: oncall@nexusdocs360.com"
    echo "- DevOps Lead: devops@nexusdocs360.com"
    exit 2
fi