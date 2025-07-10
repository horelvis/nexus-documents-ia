#!/bin/bash
# Complete VPC setup for PRE environment with proper configuration
# Based on Google Cloud VPC best practices

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
ZONE="europe-west1-b"
VPC_NAME="nexus-vpc-pre"
SUBNET_NAME="nexus-subnet-pre"
CONNECTOR_NAME="nexus-connector-pre"

echo "🔧 Setting up complete VPC configuration for PRE environment..."

# Set project
gcloud config set project $PROJECT_ID

# 1. Enable required APIs
echo "📡 Enabling required APIs..."
gcloud services enable compute.googleapis.com \
    vpcaccess.googleapis.com \
    servicenetworking.googleapis.com \
    --project=$PROJECT_ID

# 2. Create VPC network in custom mode (if not exists)
echo "🌐 Creating VPC network..."
if ! gcloud compute networks describe $VPC_NAME --project=$PROJECT_ID 2>/dev/null; then
    gcloud compute networks create $VPC_NAME \
        --subnet-mode=custom \
        --bgp-routing-mode=regional \
        --project=$PROJECT_ID
    echo "✅ VPC network created"
else
    echo "ℹ️  VPC network already exists"
fi

# 3. Create subnet with Private Google Access enabled
echo "🔀 Creating/updating subnet with Private Google Access..."
if ! gcloud compute networks subnets describe $SUBNET_NAME --region=$REGION --project=$PROJECT_ID 2>/dev/null; then
    gcloud compute networks subnets create $SUBNET_NAME \
        --network=$VPC_NAME \
        --region=$REGION \
        --range=10.1.0.0/24 \
        --enable-private-ip-google-access \
        --project=$PROJECT_ID
    echo "✅ Subnet created with Private Google Access"
else
    # Update existing subnet to enable Private Google Access
    gcloud compute networks subnets update $SUBNET_NAME \
        --region=$REGION \
        --enable-private-ip-google-access \
        --project=$PROJECT_ID
    echo "✅ Subnet updated with Private Google Access"
fi

# 4. Create firewall rules for internal communication
echo "🔥 Creating firewall rules..."
# Allow internal communication
gcloud compute firewall-rules create allow-internal-$VPC_NAME \
    --network=$VPC_NAME \
    --allow=tcp,udp,icmp \
    --source-ranges=10.1.0.0/24 \
    --project=$PROJECT_ID 2>/dev/null || echo "Firewall rule already exists"

# Allow health checks from Google
gcloud compute firewall-rules create allow-health-checks-$VPC_NAME \
    --network=$VPC_NAME \
    --allow=tcp \
    --source-ranges=35.191.0.0/16,130.211.0.0/22 \
    --project=$PROJECT_ID 2>/dev/null || echo "Health check firewall rule already exists"

# 5. Reserve IP range for VPC connector (avoiding conflicts)
echo "📍 Planning VPC connector IP range..."
# Use a high range to avoid conflicts with other resources
CONNECTOR_RANGE="10.1.240.0/28"  # Using high end of subnet range

# 6. Delete existing VPC connector if it exists
echo "🗑️  Removing existing VPC connector if present..."
if gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
    --region=$REGION --project=$PROJECT_ID 2>/dev/null; then
    
    # First remove from Cloud Run services
    echo "Removing VPC connector from services..."
    for SERVICE in nexus-backend-pre storage-service-pre; do
        gcloud run services update $SERVICE \
            --clear-vpc-connector \
            --region=$REGION \
            --project=$PROJECT_ID 2>/dev/null || true
    done
    
    # Wait for services to stabilize
    sleep 10
    
    # Delete connector
    gcloud compute networks vpc-access connectors delete $CONNECTOR_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --async \
        --quiet
    
    echo "⏳ Waiting for connector deletion..."
    sleep 30
fi

# 7. Create new VPC connector
echo "🔌 Creating VPC connector..."
gcloud compute networks vpc-access connectors create $CONNECTOR_NAME \
    --region=$REGION \
    --subnet=$SUBNET_NAME \
    --subnet-project=$PROJECT_ID \
    --min-instances=2 \
    --max-instances=3 \
    --machine-type=e2-micro \
    --project=$PROJECT_ID

# 8. Verify connector status
echo "✅ Verifying VPC connector status..."
CONNECTOR_STATE=$(gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(state)")

if [ "$CONNECTOR_STATE" = "READY" ]; then
    echo "✅ VPC connector is READY"
else
    echo "⚠️  VPC connector state: $CONNECTOR_STATE"
    echo "   Waiting for connector to be ready..."
    sleep 30
fi

# 9. Display configuration summary
echo ""
echo "📊 VPC Configuration Summary:"
echo "   - VPC Network: $VPC_NAME"
echo "   - Subnet: $SUBNET_NAME (10.1.0.0/24)"
echo "   - Private Google Access: ENABLED"
echo "   - VPC Connector: $CONNECTOR_NAME"
echo "   - Connector IP Range: $CONNECTOR_RANGE"
echo "   - Machine Type: e2-micro"
echo "   - Instances: 2-3"
echo ""
echo "🚀 To attach services to VPC connector, use:"
echo "   gcloud run services update SERVICE_NAME \\"
echo "       --vpc-connector $CONNECTOR_NAME \\"
echo "       --vpc-egress private-ranges-only \\"
echo "       --region $REGION"
echo ""
echo "✅ VPC setup complete!"