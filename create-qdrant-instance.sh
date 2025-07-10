#!/bin/bash
# Create Qdrant instance for PRE environment

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ZONE="europe-west1-b"
VPC_NAME="nexus-vpc-pre"
SUBNET_NAME="nexus-subnet-pre"

echo "🔍 Creating Qdrant instance for vector search..."

# Set project
gcloud config set project $PROJECT_ID

# Create instance
gcloud compute instances create qdrant-pre \
    --zone=$ZONE \
    --machine-type=e2-small \
    --network-interface=subnet=$SUBNET_NAME,no-address \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-standard \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=qdrant-server \
    --metadata-from-file startup-script=qdrant-startup.sh \
    --project=$PROJECT_ID

echo "⏳ Waiting for instance to be ready..."
sleep 10

# Get internal IP
QDRANT_IP=$(gcloud compute instances describe qdrant-pre \
    --zone=$ZONE \
    --format="value(networkInterfaces[0].networkIP)" \
    --project=$PROJECT_ID)

echo "✅ Qdrant instance created with internal IP: $QDRANT_IP"

# Create firewall rule
echo "🔥 Creating firewall rule..."
gcloud compute firewall-rules create allow-qdrant-pre \
    --network=$VPC_NAME \
    --allow=tcp:6333,tcp:6334 \
    --source-ranges=10.1.0.0/24 \
    --target-tags=qdrant-server \
    --project=$PROJECT_ID 2>/dev/null || echo "Firewall rule already exists"

# Update secret
echo "🔐 Updating Qdrant URL secret..."
echo "http://$QDRANT_IP:6333" | gcloud secrets create qdrant-url-pre --data-file=- --project=$PROJECT_ID 2>/dev/null || \
echo "http://$QDRANT_IP:6333" | gcloud secrets versions add qdrant-url-pre --data-file=- --project=$PROJECT_ID

echo ""
echo "✅ Qdrant setup complete!"
echo "   URL: http://$QDRANT_IP:6333"
echo "   Secret: qdrant-url-pre"