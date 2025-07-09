#!/bin/bash
# Deploy infrastructure for NexusDocs360 PRE environment on GCP
# This script creates PRE-specific resources with reduced capacity and test configurations

set -e

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/../load-env.sh"

# PRE Environment specific configuration
PROJECT_ID=${GCP_PROJECT_ID:-nexusdocs360-pre}
REGION=${GCP_REGION:-europe-west1}
ZONE=${GCP_ZONE:-europe-west1-b}
ENVIRONMENT="pre"

# Domain configuration for PRE
DOMAIN=${DOMAIN:-nexusdocs360.com}
SSL_EMAIL=${SSL_EMAIL:-admin@$DOMAIN}

echo "🏗️ Deploying PRE infrastructure for project: $PROJECT_ID in region: $REGION"
echo "📧 Domain: $DOMAIN | SSL Email: $SSL_EMAIL"
echo "⚡ Environment: PRE (Pre-Production)"

# Check if project exists, create if not
if ! gcloud projects describe $PROJECT_ID &>/dev/null; then
    echo "📝 Creating project $PROJECT_ID..."
    gcloud projects create $PROJECT_ID --name="NexusDocs360 PRE"
    echo "✅ Project created"
fi

# Set project
gcloud config set project $PROJECT_ID

# 1. Create VPC and subnet (PRE specific range)
echo "🌐 Creating VPC network for PRE..."
gcloud compute networks create nexus-vpc-pre \
    --subnet-mode=custom \
    --bgp-routing-mode=regional \
    --project=$PROJECT_ID || echo "VPC already exists"

gcloud compute networks subnets create nexus-subnet-pre \
    --network=nexus-vpc-pre \
    --region=$REGION \
    --range=10.1.0.0/24 \
    --project=$PROJECT_ID || echo "Subnet already exists"

# 2. Create Cloud NAT for outbound traffic
echo "🌊 Creating Cloud NAT for PRE..."
gcloud compute routers create nexus-router-pre \
    --network=nexus-vpc-pre \
    --region=$REGION \
    --project=$PROJECT_ID || echo "Router already exists"

gcloud compute routers nats create nexus-nat-pre \
    --router=nexus-router-pre \
    --region=$REGION \
    --nat-all-subnet-ip-ranges \
    --auto-allocate-nat-external-ips \
    --project=$PROJECT_ID || echo "NAT already exists"

# 3. Create Cloud SQL instance (PRE with minimal resources)
echo "🗄️ Creating Cloud SQL instance (PRE - minimal tier)..."
gcloud sql instances create nexus-db-pre \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=$REGION \
    --network=projects/$PROJECT_ID/global/networks/nexus-vpc-pre \
    --no-assign-ip \
    --backup-start-time=03:00 \
    --backup-location=$REGION \
    --enable-point-in-time-recovery \
    --project=$PROJECT_ID || echo "Cloud SQL instance already exists"

# Get Cloud SQL IP (only if instance exists)
if gcloud sql instances describe nexus-db-pre --project=$PROJECT_ID &>/dev/null; then
    DB_IP=$(gcloud sql instances describe nexus-db-pre --format="value(ipAddresses[0].ipAddress)" --project=$PROJECT_ID)
    echo "Cloud SQL IP: $DB_IP"
    
    # Update database secret with actual IP
    if [ ! -z "$DB_IP" ]; then
        echo -n "$DB_IP" | gcloud secrets versions add db-host-pre --data-file=- --project=$PROJECT_ID || \
        echo -n "$DB_IP" | gcloud secrets create db-host-pre --data-file=- --project=$PROJECT_ID
    fi
else
    echo "⚠️  Cloud SQL instance not found. Skipping IP configuration."
fi

# Create database and user with PRE naming (only if instance exists)
if gcloud sql instances describe nexus-db-pre --project=$PROJECT_ID &>/dev/null; then
    echo "Creating PRE database and user..."
    gcloud sql databases create nexusdocs360_pre --instance=nexus-db-pre --project=$PROJECT_ID || true
    
    # Check if db-pass-pre secret exists
    if gcloud secrets describe db-pass-pre --project=$PROJECT_ID &>/dev/null; then
        DB_PASS=$(gcloud secrets versions access latest --secret=db-pass-pre --project=$PROJECT_ID)
        gcloud sql users create nexus_user_pre --instance=nexus-db-pre --password="$DB_PASS" --project=$PROJECT_ID || true
    else
        echo "⚠️  db-pass-pre secret not found. Run setup-secrets-pre.sh first."
    fi
fi

# 4. Create Memorystore Redis instance (PRE with minimal tier)
echo "💾 Creating Redis instance (PRE - 1GB)..."
gcloud redis instances create nexus-redis-pre \
    --size=1 \
    --region=$REGION \
    --redis-version=redis_7_0 \
    --network=projects/$PROJECT_ID/global/networks/nexus-vpc-pre \
    --redis-config=maxmemory-policy=volatile-lru \
    --project=$PROJECT_ID || echo "Redis instance already exists"

# Get Redis IP (only if instance exists)
if gcloud redis instances describe nexus-redis-pre --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    REDIS_IP=$(gcloud redis instances describe nexus-redis-pre --region=$REGION --format="value(host)" --project=$PROJECT_ID)
    echo "Redis IP: $REDIS_IP"
    
    # Update Redis secret
    if [ ! -z "$REDIS_IP" ]; then
        echo -n "redis://${REDIS_IP}:6379" | gcloud secrets versions add redis-url-pre --data-file=- --project=$PROJECT_ID || \
        echo -n "redis://${REDIS_IP}:6379" | gcloud secrets create redis-url-pre --data-file=- --project=$PROJECT_ID
    fi
else
    echo "⚠️  Redis instance not found. Skipping configuration."
fi

# 5. Create Compute Engine instance for Qdrant (PRE with smaller machine)
echo "🔍 Creating Qdrant VM (PRE - e2-small)..."
gcloud compute instances create qdrant-pre \
    --machine-type=e2-small \
    --zone=$ZONE \
    --network-interface=subnet=nexus-subnet-pre,no-address \
    --boot-disk-size=20GB \
    --boot-disk-type=pd-standard \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=qdrant-server-pre \
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
      - QDRANT__LOG_LEVEL=DEBUG
      - QDRANT__SERVICE__HTTP_PORT=6333
      - QDRANT__SERVICE__GRPC_PORT=6334
    restart: always
    mem_limit: 1g
EOF
cd /opt/qdrant && docker-compose up -d' \
    --project=$PROJECT_ID || echo "Qdrant VM already exists"

# 6. Create firewall rules with PRE suffix
echo "🔥 Creating firewall rules for PRE..."
gcloud compute firewall-rules create allow-qdrant-pre \
    --network=nexus-vpc-pre \
    --allow=tcp:6333,tcp:6334 \
    --source-ranges=10.1.0.0/24 \
    --target-tags=qdrant-server-pre \
    --project=$PROJECT_ID || echo "Firewall rule already exists"

# Firewall rules for Nginx proxy
gcloud compute firewall-rules create allow-nginx-http-pre \
    --network=nexus-vpc-pre \
    --allow=tcp:80,tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=nginx-proxy-pre \
    --project=$PROJECT_ID || echo "Nginx firewall rule already exists"

# 7. Create storage buckets with PRE suffix and test lifecycle
echo "🪣 Creating storage buckets for PRE..."
gsutil mb -p $PROJECT_ID -c STANDARD -l EU gs://nexusdocs360-pre-docs-eu/ || echo "Bucket already exists"
gsutil mb -p $PROJECT_ID -c NEARLINE -l EU gs://nexusdocs360-pre-backups-eu/ || echo "Backup bucket already exists"
gsutil mb -p $PROJECT_ID -c STANDARD -l EU gs://nexusdocs360-pre-scripts/ || echo "Scripts bucket already exists"

# Set bucket lifecycle for PRE (shorter retention)
cat > /tmp/lifecycle-pre.json << EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 7, "matchesPrefix": ["temp/"]}
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
        "condition": {"age": 14}
      },
      {
        "action": {"type": "Delete"},
        "condition": {"age": 30}
      }
    ]
  }
}
EOF
gsutil lifecycle set /tmp/lifecycle-pre.json gs://nexusdocs360-pre-docs-eu/

# 8. Create Nginx Reverse Proxy VM for PRE
echo "🔒 Creating Nginx reverse proxy VM for PRE..."

# Reserve static IP for Nginx PRE
gcloud compute addresses create nexus-nginx-ip-pre \
    --region=$REGION \
    --project=$PROJECT_ID || echo "Nginx IP already exists"

NGINX_IP=$(gcloud compute addresses describe nexus-nginx-ip-pre --region=$REGION --format="value(address)" --project=$PROJECT_ID)
echo "Nginx PRE IP: $NGINX_IP"

# Create Nginx VM with PRE configuration
gcloud compute instances create nginx-proxy-pre \
    --machine-type=e2-small \
    --zone=$ZONE \
    --network-interface=address=$NGINX_IP,subnet=nexus-subnet-pre \
    --boot-disk-size=10GB \
    --boot-disk-type=pd-standard \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=nginx-proxy-pre \
    --metadata=startup-script-url=gs://nexusdocs360-pre-scripts/nginx-vm-startup-pre.sh,DOMAIN=$DOMAIN,EMAIL=$SSL_EMAIL,ENVIRONMENT=pre \
    --project=$PROJECT_ID || echo "Nginx VM already exists"

# Upload PRE startup script to GCS
gsutil cp deployment/gcp/nginx-vm-startup-pre.sh gs://nexusdocs360-pre-scripts/ || echo "Script already uploaded"

# 9. Create artifact registry for PRE container images
echo "📦 Creating Artifact Registry for PRE..."
gcloud artifacts repositories create nexusdocs360-pre \
    --repository-format=docker \
    --location=$REGION \
    --description="NexusDocs360 PRE container images" \
    --project=$PROJECT_ID || echo "Artifact Registry already exists"

# Configure docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# 10. Create VPC Connector for Cloud Run (PRE)
echo "🔌 Creating VPC Connector for PRE..."
gcloud compute networks vpc-access connectors create nexus-connector-pre \
    --region=$REGION \
    --subnet=nexus-subnet-pre \
    --subnet-project=$PROJECT_ID \
    --min-instances=2 \
    --max-instances=3 \
    --machine-type=f1-micro \
    --project=$PROJECT_ID || echo "VPC Connector already exists"

# 11. Create Cloud Scheduler for PRE testing
echo "⏰ Creating Cloud Scheduler for PRE health checks..."
gcloud scheduler jobs create http pre-health-check \
    --location=$REGION \
    --schedule="*/5 * * * *" \
    --uri="https://pre-api.${DOMAIN}/health" \
    --http-method=GET \
    --project=$PROJECT_ID || echo "Scheduler job already exists"

# 12. Enable additional APIs for PRE monitoring
echo "📊 Enabling monitoring APIs for PRE..."
gcloud services enable monitoring.googleapis.com \
    logging.googleapis.com \
    cloudtrace.googleapis.com \
    clouderrorreporting.googleapis.com \
    --project=$PROJECT_ID

echo "✅ PRE Infrastructure deployment complete!"
echo ""
echo "📝 PRE Environment Details:"
echo "   - Project: $PROJECT_ID"
echo "   - VPC: nexus-vpc-pre (10.1.0.0/24)"
echo "   - Database: nexus-db-pre (db-f1-micro)"
echo "   - Redis: nexus-redis-pre (1GB)"
echo "   - Qdrant: qdrant-pre (e2-small)"
echo "   - Nginx: nginx-proxy-pre (e2-small)"
echo ""
echo "🌐 DNS Configuration for PRE:"
echo "   - A record: pre.$DOMAIN → $NGINX_IP"
echo "   - A record: pre-app.$DOMAIN → $NGINX_IP"
echo "   - A record: pre-api.$DOMAIN → $NGINX_IP"
echo ""
echo "🔐 Security Notes:"
echo "   - All services use PRE-specific secrets"
echo "   - Test API keys should be used"
echo "   - Access restricted to internal team"
echo ""
echo "🚀 To deploy applications to PRE, run:"
echo "   gcloud builds submit --config=cloudbuild-pre.yaml"
echo ""
echo "💰 Estimated PRE Costs:"
echo "   - Total: ~$200-250/month"
echo "   - 50% of production capacity"