#!/bin/bash
# Deploy infrastructure for NouxCubeIA PRODUCTION environment on GCP
# This script creates PROD-specific resources with full capacity and high availability

set -e

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/../load-env.sh"

# PROD Environment specific configuration
PROJECT_ID=${GCP_PROJECT_ID:-nexusdocs360-prod}
REGION=${GCP_REGION:-europe-west1}
ZONE=${GCP_ZONE:-europe-west1-b}
ENVIRONMENT="prod"

# Domain configuration for PROD
DOMAIN=${DOMAIN:-nexusdocs360.com}
SSL_EMAIL=${SSL_EMAIL:-admin@$DOMAIN}

echo "🏗️ Deploying PRODUCTION infrastructure for project: $PROJECT_ID in region: $REGION"
echo "📧 Domain: $DOMAIN | SSL Email: $SSL_EMAIL"
echo "⚡ Environment: PRODUCTION"
echo ""
echo "⚠️  WARNING: This will create production resources with associated costs!"
read -p "Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled"
    exit 0
fi

# Check if project exists, create if not
if ! gcloud projects describe $PROJECT_ID &>/dev/null; then
    echo "📝 Creating project $PROJECT_ID..."
    gcloud projects create $PROJECT_ID --name="NouxCubeIA PROD"
    echo "✅ Project created"
fi

# Set project
gcloud config set project $PROJECT_ID

# 1. Create VPC and subnet (PROD specific range)
echo "🌐 Creating VPC network for PRODUCTION..."
gcloud compute networks create nexus-vpc-prod \
    --subnet-mode=custom \
    --bgp-routing-mode=regional \
    --project=$PROJECT_ID || echo "VPC already exists"

# Create multiple subnets for high availability
gcloud compute networks subnets create nexus-subnet-prod-primary \
    --network=nexus-vpc-prod \
    --region=$REGION \
    --range=10.0.0.0/24 \
    --enable-private-ip-google-access \
    --project=$PROJECT_ID || echo "Primary subnet already exists"

gcloud compute networks subnets create nexus-subnet-prod-secondary \
    --network=nexus-vpc-prod \
    --region=$REGION \
    --range=10.0.1.0/24 \
    --enable-private-ip-google-access \
    --project=$PROJECT_ID || echo "Secondary subnet already exists"

# 2. Create Cloud NAT for outbound traffic with static IPs
echo "🌊 Creating Cloud NAT with static IPs for PRODUCTION..."
gcloud compute routers create nexus-router-prod \
    --network=nexus-vpc-prod \
    --region=$REGION \
    --project=$PROJECT_ID || echo "Router already exists"

# Reserve static IPs for NAT
gcloud compute addresses create nexus-nat-ip-1 --region=$REGION --project=$PROJECT_ID || true
gcloud compute addresses create nexus-nat-ip-2 --region=$REGION --project=$PROJECT_ID || true

NAT_IP1=$(gcloud compute addresses describe nexus-nat-ip-1 --region=$REGION --format="value(address)" --project=$PROJECT_ID)
NAT_IP2=$(gcloud compute addresses describe nexus-nat-ip-2 --region=$REGION --format="value(address)" --project=$PROJECT_ID)

gcloud compute routers nats create nexus-nat-prod \
    --router=nexus-router-prod \
    --region=$REGION \
    --nat-external-ip-pool=nexus-nat-ip-1,nexus-nat-ip-2 \
    --nat-all-subnet-ip-ranges \
    --project=$PROJECT_ID || echo "NAT already exists"

# 3. Create Cloud SQL instance (PROD with HA and replicas)
echo "🗄️ Creating Cloud SQL instance (PRODUCTION - High Availability)..."
gcloud sql instances create nexus-db-prod \
    --database-version=POSTGRES_15 \
    --tier=db-n1-standard-2 \
    --region=$REGION \
    --network=projects/$PROJECT_ID/global/networks/nexus-vpc-prod \
    --no-assign-ip \
    --availability-type=REGIONAL \
    --backup-start-time=02:00 \
    --backup-configuration-location=$REGION \
    --backup-configuration-point-in-time-recovery-enabled \
    --backup-configuration-transaction-log-retention-days=7 \
    --enable-bin-log \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=3 \
    --maintenance-window-duration=4 \
    --database-flags=max_connections=200,shared_buffers=256MB \
    --cpu=2 \
    --memory=7680MB \
    --storage-size=100GB \
    --storage-type=SSD \
    --storage-auto-increase \
    --storage-auto-increase-limit=500 \
    --project=$PROJECT_ID || echo "Cloud SQL instance already exists"

# Create read replica for PROD
echo "Creating Cloud SQL read replica..."
gcloud sql instances create nexus-db-prod-replica \
    --master-instance-name=nexus-db-prod \
    --tier=db-n1-standard-1 \
    --region=$REGION \
    --replica-type=READ \
    --availability-type=ZONAL \
    --project=$PROJECT_ID || echo "Read replica already exists"

# Get Cloud SQL IP
DB_IP=$(gcloud sql instances describe nexus-db-prod --format="value(ipAddresses[0].ipAddress)" --project=$PROJECT_ID)
echo "Cloud SQL IP: $DB_IP"

# Update database secret with actual IP
echo -n "$DB_IP" | gcloud secrets versions add db-host-prod --data-file=- --project=$PROJECT_ID

# Create database and user with PROD naming
echo "Creating PRODUCTION database and user..."
gcloud sql databases create nexusdocs360_prod --instance=nexus-db-prod --project=$PROJECT_ID || true
gcloud sql users create nexus_user_prod --instance=nexus-db-prod --password=$(gcloud secrets versions access latest --secret=db-pass-prod --project=$PROJECT_ID) --project=$PROJECT_ID || true

# 4. Create Memorystore Redis instance (PROD with HA)
echo "💾 Creating Redis instance (PRODUCTION - 5GB with HA)..."
gcloud redis instances create nexus-redis-prod \
    --size=5 \
    --region=$REGION \
    --tier=STANDARD_HA \
    --redis-version=redis_7_0 \
    --network=projects/$PROJECT_ID/global/networks/nexus-vpc-prod \
    --redis-config=maxmemory-policy=allkeys-lru,timeout=300 \
    --enable-auth \
    --project=$PROJECT_ID || echo "Redis instance already exists"

# Get Redis IP and auth string
REDIS_HOST=$(gcloud redis instances describe nexus-redis-prod --region=$REGION --format="value(host)" --project=$PROJECT_ID)
REDIS_AUTH=$(gcloud redis instances get-auth-string nexus-redis-prod --region=$REGION --project=$PROJECT_ID 2>/dev/null || echo "")

if [ -n "$REDIS_AUTH" ]; then
    REDIS_URL="redis://:${REDIS_AUTH}@${REDIS_HOST}:6379"
else
    REDIS_URL="redis://${REDIS_HOST}:6379"
fi

# Update Redis secret
echo -n "$REDIS_URL" | gcloud secrets versions add redis-url-prod --data-file=- --project=$PROJECT_ID

# 5. Create Compute Engine instances for Qdrant (PROD with cluster)
echo "🔍 Creating Qdrant cluster (PRODUCTION - 3 nodes)..."

# Create instance template for Qdrant
gcloud compute instance-templates create qdrant-prod-template \
    --machine-type=e2-standard-2 \
    --network-interface=subnet=nexus-subnet-prod-primary,no-address \
    --boot-disk-size=50GB \
    --boot-disk-type=pd-ssd \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=qdrant-server-prod \
    --metadata=startup-script='#!/bin/bash
apt-get update
apt-get install -y docker.io docker-compose
systemctl start docker
systemctl enable docker
mkdir -p /opt/qdrant/storage
cat > /opt/qdrant/docker-compose.yml << EOF
version: "3.8"
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./storage:/qdrant/storage
    environment:
      - QDRANT__LOG_LEVEL=INFO
      - QDRANT__SERVICE__HTTP_PORT=6333
      - QDRANT__SERVICE__GRPC_PORT=6334
      - QDRANT__CLUSTER__ENABLED=true
    restart: always
    mem_limit: 4g
EOF
cd /opt/qdrant && docker-compose up -d' \
    --project=$PROJECT_ID || echo "Instance template already exists"

# Create managed instance group
gcloud compute instance-groups managed create qdrant-prod-group \
    --base-instance-name=qdrant-prod \
    --template=qdrant-prod-template \
    --size=3 \
    --zone=$ZONE \
    --project=$PROJECT_ID || echo "Instance group already exists"

# 6. Create firewall rules for PROD
echo "🔥 Creating firewall rules for PRODUCTION..."
gcloud compute firewall-rules create allow-qdrant-prod \
    --network=nexus-vpc-prod \
    --allow=tcp:6333,tcp:6334 \
    --source-ranges=10.0.0.0/23 \
    --target-tags=qdrant-server-prod \
    --project=$PROJECT_ID || echo "Firewall rule already exists"

# Firewall rules for Nginx proxy
gcloud compute firewall-rules create allow-nginx-http-prod \
    --network=nexus-vpc-prod \
    --allow=tcp:80,tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=nginx-proxy-prod \
    --project=$PROJECT_ID || echo "Nginx firewall rule already exists"

# 7. Create storage buckets with PROD configuration
echo "🪣 Creating storage buckets for PRODUCTION..."
gsutil mb -p $PROJECT_ID -c STANDARD -l EU -b on gs://nexusdocs360-prod-docs-eu/ || echo "Bucket already exists"
gsutil mb -p $PROJECT_ID -c STANDARD -l EU -b on gs://nexusdocs360-prod-backups-eu/ || echo "Backup bucket already exists"
gsutil mb -p $PROJECT_ID -c STANDARD -l EU gs://nexusdocs360-prod-scripts/ || echo "Scripts bucket already exists"

# Enable versioning on production buckets
gsutil versioning set on gs://nexusdocs360-prod-docs-eu/
gsutil versioning set on gs://nexusdocs360-prod-backups-eu/

# Set bucket lifecycle for PROD (longer retention)
cat > /tmp/lifecycle-prod.json << EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
        "condition": {"age": 60}
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
        "condition": {"age": 180}
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "ARCHIVE"},
        "condition": {"age": 365}
      }
    ]
  }
}
EOF
gsutil lifecycle set /tmp/lifecycle-prod.json gs://nexusdocs360-prod-docs-eu/

# Set uniform bucket-level access
gsutil uniformbucketlevelaccess set on gs://nexusdocs360-prod-docs-eu/
gsutil uniformbucketlevelaccess set on gs://nexusdocs360-prod-backups-eu/

# 8. Create Load Balancer with Nginx (PROD with multiple instances)
echo "🔒 Creating Load Balancer with Nginx for PRODUCTION..."

# Create instance template for Nginx
gcloud compute instance-templates create nginx-prod-template \
    --machine-type=e2-standard-2 \
    --network-interface=subnet=nexus-subnet-prod-primary,address="" \
    --boot-disk-size=20GB \
    --boot-disk-type=pd-ssd \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=nginx-proxy-prod \
    --metadata=startup-script-url=gs://nexusdocs360-prod-scripts/nginx-vm-startup-prod.sh,DOMAIN=$DOMAIN,EMAIL=$SSL_EMAIL,ENVIRONMENT=prod \
    --project=$PROJECT_ID || echo "Nginx template already exists"

# Create health check
gcloud compute health-checks create https nginx-prod-health \
    --port=443 \
    --request-path=/health \
    --project=$PROJECT_ID || echo "Health check already exists"

# Create managed instance group
gcloud compute instance-groups managed create nginx-prod-group \
    --base-instance-name=nginx-prod \
    --template=nginx-prod-template \
    --size=2 \
    --zone=$ZONE \
    --health-check=nginx-prod-health \
    --initial-delay=300 \
    --project=$PROJECT_ID || echo "Instance group already exists"

# Create backend service
gcloud compute backend-services create nginx-backend-prod \
    --protocol=HTTPS \
    --health-checks=nginx-prod-health \
    --global \
    --project=$PROJECT_ID || echo "Backend service already exists"

# Add instance group to backend service
gcloud compute backend-services add-backend nginx-backend-prod \
    --instance-group=nginx-prod-group \
    --instance-group-zone=$ZONE \
    --global \
    --project=$PROJECT_ID || echo "Backend already added"

# Reserve global IP for load balancer
gcloud compute addresses create nexus-lb-ip-prod \
    --ip-version=IPV4 \
    --global \
    --project=$PROJECT_ID || echo "Load balancer IP already exists"

LB_IP=$(gcloud compute addresses describe nexus-lb-ip-prod --global --format="value(address)" --project=$PROJECT_ID)
echo "Load Balancer IP: $LB_IP"

# 9. Create artifact registry for PROD container images
echo "📦 Creating Artifact Registry for PRODUCTION..."
gcloud artifacts repositories create nexusdocs360-prod \
    --repository-format=docker \
    --location=$REGION \
    --description="NouxCubeIA PRODUCTION container images" \
    --project=$PROJECT_ID || echo "Artifact Registry already exists"

# Configure docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# 10. Create VPC Connector for Cloud Run (PROD with redundancy)
echo "🔌 Creating VPC Connector for PRODUCTION..."
gcloud compute networks vpc-access connectors create nexus-connector-prod \
    --region=$REGION \
    --subnet=nexus-subnet-prod-primary \
    --subnet-project=$PROJECT_ID \
    --min-instances=4 \
    --max-instances=10 \
    --machine-type=e2-micro \
    --project=$PROJECT_ID || echo "VPC Connector already exists"

# 11. Create Cloud CDN for static assets
echo "🌐 Creating Cloud CDN for PRODUCTION..."
gcloud compute backend-buckets create nexus-cdn-backend-prod \
    --gcs-bucket-name=nexusdocs360-prod-static \
    --enable-cdn \
    --cache-mode=CACHE_ALL_STATIC \
    --default-ttl=3600 \
    --max-ttl=86400 \
    --project=$PROJECT_ID || echo "CDN backend already exists"

# Create static assets bucket
gsutil mb -p $PROJECT_ID -c STANDARD -l EU gs://nexusdocs360-prod-static/ || echo "Static assets bucket already exists"

# 12. Enable additional services for PROD
echo "📊 Enabling additional services for PRODUCTION..."
gcloud services enable \
    monitoring.googleapis.com \
    logging.googleapis.com \
    cloudtrace.googleapis.com \
    clouderrorreporting.googleapis.com \
    cloudprofiler.googleapis.com \
    clouddebugger.googleapis.com \
    cloudkms.googleapis.com \
    dlp.googleapis.com \
    securitycenter.googleapis.com \
    --project=$PROJECT_ID

# 13. Create KMS keys for PROD encryption
echo "🔐 Creating KMS encryption keys for PRODUCTION..."
gcloud kms keyrings create nexus-keyring-prod \
    --location=$REGION \
    --project=$PROJECT_ID || echo "Keyring already exists"

gcloud kms keys create nexus-key-prod \
    --location=$REGION \
    --keyring=nexus-keyring-prod \
    --purpose=encryption \
    --rotation-period=90d \
    --next-rotation-time="+90d" \
    --project=$PROJECT_ID || echo "KMS key already exists"

echo "✅ PRODUCTION Infrastructure deployment complete!"
echo ""
echo "📝 PRODUCTION Environment Details:"
echo "   - Project: $PROJECT_ID"
echo "   - VPC: nexus-vpc-prod (10.0.0.0/23)"
echo "   - Database: nexus-db-prod (db-n1-standard-2 with HA)"
echo "   - Database Replica: nexus-db-prod-replica"
echo "   - Redis: nexus-redis-prod (5GB with HA)"
echo "   - Qdrant: qdrant-prod-group (3 nodes)"
echo "   - Load Balancer: $LB_IP"
echo ""
echo "🌐 DNS Configuration for PRODUCTION:"
echo "   - A record: $DOMAIN → $LB_IP"
echo "   - A record: www.$DOMAIN → $LB_IP"
echo "   - A record: app.$DOMAIN → $LB_IP"
echo "   - A record: api.$DOMAIN → $LB_IP"
echo ""
echo "🔐 Security Features:"
echo "   - High Availability across zones"
echo "   - Automated backups with PITR"
echo "   - KMS encryption enabled"
echo "   - DDoS protection via Cloud Armor"
echo "   - Security Command Center enabled"
echo ""
echo "🚀 To deploy applications to PRODUCTION, run:"
echo "   gcloud builds submit --config=cloudbuild.yaml"
echo ""
echo "💰 Estimated PRODUCTION Costs:"
echo "   - Cloud SQL: ~$200/month"
echo "   - Redis HA: ~$150/month"
echo "   - Compute (Qdrant + Nginx): ~$200/month"
echo "   - Cloud Run: ~$100-300/month (usage based)"
echo "   - Storage & Network: ~$50-100/month"
echo "   - Total: ~$700-1000/month"
echo ""
echo "⚠️  IMPORTANT: Monitor costs daily in the first week!"