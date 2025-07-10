#!/bin/bash
# Create Redis Memorystore instance for PRE environment

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ZONE="europe-west1-b"
VPC_NAME="nexus-vpc-pre"

echo "💾 Creating Redis Memorystore instance..."

# Set project
gcloud config set project $PROJECT_ID

# Create Redis instance
echo "Creating Redis instance (this may take 5-10 minutes)..."
gcloud redis instances create nexus-redis-pre \
    --size=1 \
    --region=$REGION \
    --tier=BASIC \
    --redis-version=redis_7_0 \
    --network=projects/$PROJECT_ID/global/networks/$VPC_NAME \
    --redis-config=maxmemory-policy=volatile-lru \
    --project=$PROJECT_ID

# Get Redis IP
echo "Getting Redis instance details..."
REDIS_IP=$(gcloud redis instances describe nexus-redis-pre \
    --region=$REGION \
    --format="value(host)" \
    --project=$PROJECT_ID)

# Update Redis URL secret
echo "🔐 Updating Redis URL secret..."
echo "redis://${REDIS_IP}:6379" | gcloud secrets versions add redis-url-pre --data-file=- --project=$PROJECT_ID

echo ""
echo "✅ Redis Memorystore setup complete!"
echo "   Host: $REDIS_IP"
echo "   Port: 6379"
echo "   URL: redis://${REDIS_IP}:6379"
echo "   Secret: redis-url-pre"
echo ""
echo "📝 Note: Redis is only accessible within the VPC"