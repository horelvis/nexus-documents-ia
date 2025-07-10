#!/bin/bash
# Recreate VM instances for PRE environment after VPC cleanup

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ZONE="europe-west1-b"
VPC_NAME="nexus-vpc-pre"
SUBNET_NAME="nexus-subnet-pre"

echo "🚀 Recreating VM instances for PRE environment"
echo "============================================="
echo ""

# Set project
gcloud config set project $PROJECT_ID

# 1. Create Qdrant instance for vector search
echo "🔍 Creating Qdrant instance..."
gcloud compute instances create qdrant-pre \
    --zone=$ZONE \
    --machine-type=e2-small \
    --network-interface=subnet=$SUBNET_NAME,no-address \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-standard \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=qdrant-server \
    --metadata=startup-script='#!/bin/bash
apt-get update
apt-get install -y docker.io docker-compose
systemctl start docker
systemctl enable docker

# Create Qdrant directory
mkdir -p /opt/qdrant/storage

# Create docker-compose file
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
    restart: always
    mem_limit: 1g
EOF

# Start Qdrant
cd /opt/qdrant && docker-compose up -d

# Wait for Qdrant to be ready
sleep 30

# Create collections for NexusDocs360
curl -X PUT "http://localhost:6333/collections/documents" \
  -H "Content-Type: application/json" \
  -d '\''{"vectors": {"size": 1536, "distance": "Cosine"}}'\''

echo "Qdrant setup complete"' \
    --project=$PROJECT_ID || echo "Qdrant instance already exists"

# Get Qdrant internal IP
QDRANT_IP=$(gcloud compute instances describe qdrant-pre \
    --zone=$ZONE \
    --format="value(networkInterfaces[0].networkIP)" \
    --project=$PROJECT_ID)

echo "✅ Qdrant instance created with internal IP: $QDRANT_IP"

# 2. Create/Update firewall rules
echo ""
echo "🔥 Creating firewall rules..."

# Allow Qdrant traffic
gcloud compute firewall-rules create allow-qdrant-pre \
    --network=$VPC_NAME \
    --allow=tcp:6333,tcp:6334 \
    --source-ranges=10.1.0.0/24 \
    --target-tags=qdrant-server \
    --project=$PROJECT_ID 2>/dev/null || echo "Firewall rule already exists"

# Allow internal traffic
gcloud compute firewall-rules create allow-internal-pre \
    --network=$VPC_NAME \
    --allow=tcp,udp,icmp \
    --source-ranges=10.1.0.0/24 \
    --project=$PROJECT_ID 2>/dev/null || echo "Internal firewall rule already exists"

# 3. Update secrets with Qdrant URL
echo ""
echo "🔐 Updating Qdrant URL secret..."
echo "http://$QDRANT_IP:6333" | gcloud secrets versions add qdrant-url-pre --data-file=- --project=$PROJECT_ID 2>/dev/null || {
    # Create secret if it doesn't exist
    gcloud secrets create qdrant-url-pre --data-file=- --project=$PROJECT_ID <<< "http://$QDRANT_IP:6333"
}

# 4. Display summary
echo ""
echo "📊 VM Instances Summary:"
echo "========================"
echo ""
echo "✅ Qdrant Vector Database:"
echo "   - Instance: qdrant-pre"
echo "   - Internal IP: $QDRANT_IP"
echo "   - Ports: 6333 (HTTP), 6334 (gRPC)"
echo "   - URL: http://$QDRANT_IP:6333"
echo ""
echo "📝 Notes:"
echo "   - Qdrant is only accessible within the VPC"
echo "   - Cloud Run services can connect via VPC connector"
echo "   - No external IP for security"
echo ""
echo "🔗 Connection from Cloud Run services:"
echo "   Use the secret 'qdrant-url-pre' or URL: http://$QDRANT_IP:6333"
echo ""
echo "✅ VM instances recreation complete!"