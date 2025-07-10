#!/bin/bash
# Quick VPC fix script for common VPC connector issues
# This script implements the proven solution for VPC connector problems

set -e

PROJECT_ID=${1:-nexusdocs360-pre}
REGION=${2:-europe-west1}
VPC_NAME="nexus-vpc-${PROJECT_ID##*-}"
SUBNET_NAME="nexus-subnet-${PROJECT_ID##*-}"
CONNECTOR_NAME="nexus-connector-${PROJECT_ID##*-}"

echo "🔧 Quick VPC Fix for project: $PROJECT_ID"
echo "   VPC: $VPC_NAME"
echo "   Subnet: $SUBNET_NAME"
echo "   Connector: $CONNECTOR_NAME"
echo ""

# Set project
gcloud config set project $PROJECT_ID

# Check if subnet has Private Google Access enabled
echo "🔍 Checking subnet configuration..."
PRIVATE_ACCESS=$(gcloud compute networks subnets describe $SUBNET_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(privateIpGoogleAccess)" 2>/dev/null || echo "false")

if [ "$PRIVATE_ACCESS" != "True" ]; then
    echo "❌ Private Google Access is not enabled!"
    echo "🔧 Enabling Private Google Access on subnet..."
    gcloud compute networks subnets update $SUBNET_NAME \
        --region=$REGION \
        --enable-private-ip-google-access \
        --project=$PROJECT_ID
    echo "✅ Private Google Access enabled"
else
    echo "✅ Private Google Access is already enabled"
fi

# Check VPC connector state
echo ""
echo "🔍 Checking VPC connector status..."
CONNECTOR_STATE=$(gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(state)" 2>/dev/null || echo "NOT_FOUND")

if [ "$CONNECTOR_STATE" = "READY" ]; then
    echo "✅ VPC connector is already READY"
    exit 0
fi

echo "⚠️  VPC connector state: $CONNECTOR_STATE"

# If connector exists but not ready, delete it
if [ "$CONNECTOR_STATE" != "NOT_FOUND" ]; then
    echo "🗑️  Deleting existing VPC connector..."
    
    # First detach from Cloud Run services
    echo "Detaching from Cloud Run services..."
    SERVICES=$(gcloud run services list --region=$REGION --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
    for SERVICE in $SERVICES; do
        gcloud run services update $SERVICE \
            --clear-vpc-connector \
            --region=$REGION \
            --project=$PROJECT_ID 2>/dev/null || true
    done
    
    # Delete connector
    gcloud compute networks vpc-access connectors delete $CONNECTOR_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --quiet --async
    
    # Wait for deletion
    echo "⏳ Waiting for connector deletion (up to 3 minutes)..."
    for i in {1..18}; do
        STATE=$(gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
            --region=$REGION --project=$PROJECT_ID --format="value(state)" 2>/dev/null || echo "DELETED")
        if [ "$STATE" = "DELETED" ]; then
            echo "✅ Connector deleted"
            break
        fi
        sleep 10
    done
fi

# Create new VPC connector
echo ""
echo "🔌 Creating VPC connector with proper configuration..."
gcloud compute networks vpc-access connectors create $CONNECTOR_NAME \
    --region=$REGION \
    --network=$VPC_NAME \
    --range=10.1.240.0/28 \
    --min-instances=2 \
    --max-instances=3 \
    --machine-type=e2-micro \
    --project=$PROJECT_ID

# Wait for connector to be ready
echo "⏳ Waiting for connector to be ready..."
for i in {1..12}; do
    STATE=$(gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
        --region=$REGION --project=$PROJECT_ID --format="value(state)" 2>/dev/null || echo "CREATING")
    if [ "$STATE" = "READY" ]; then
        echo "✅ VPC connector is READY"
        break
    fi
    echo "   State: $STATE (attempt $i/12)"
    sleep 10
done

# Final verification
echo ""
echo "📊 Final VPC connector status:"
gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
    --region=$REGION --project=$PROJECT_ID --format=yaml | grep -E "state:|ipCidrRange:|machineType:"

echo ""
echo "✅ VPC fix complete!"
echo ""
echo "To attach services to VPC connector, use:"
echo "  gcloud run services update SERVICE_NAME \\"
echo "      --vpc-connector $CONNECTOR_NAME \\"
echo "      --vpc-egress private-ranges-only \\"
echo "      --region $REGION"