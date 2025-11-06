#!/bin/bash

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"

echo "=== Fixing VPC Connector for PRE environment ==="
echo ""

# Step 1: Remove VPC connector from all Cloud Run services
echo "Step 1: Removing VPC connector from Cloud Run services..."
for service in nexus-backend-pre storage-service-pre nexus-frontend-pre; do
  echo "Updating $service..."
  gcloud run services update $service \
    --region=$REGION \
    --project=$PROJECT_ID \
    --clear-vpc-connector 2>/dev/null || echo "Service $service not found or already cleared"
done

echo ""
echo "Waiting for services to stabilize..."
sleep 30

# Step 2: Delete the problematic VPC connector
echo ""
echo "Step 2: Attempting to delete the problematic VPC connector..."
gcloud compute networks vpc-access connectors delete nexus-connector-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --quiet || echo "Could not delete connector, it may be in use or already deleted"

echo ""
echo "Waiting for deletion to complete..."
sleep 60

# Step 3: Create a new VPC connector
echo ""
echo "Step 3: Creating new VPC connector..."

# First, get the subnet CIDR range
SUBNET_RANGE=$(gcloud compute networks subnets describe nexus-subnet-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="value(ipCidrRange)")

echo "Subnet range: $SUBNET_RANGE"

# Create the connector
gcloud compute networks vpc-access connectors create nexus-connector-pre \
  --region=$REGION \
  --subnet=nexus-subnet-pre \
  --subnet-project=$PROJECT_ID \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro \
  --project=$PROJECT_ID

# Step 4: Verify the connector
echo ""
echo "Step 4: Verifying VPC connector..."
gcloud compute networks vpc-access connectors describe nexus-connector-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="table(name,state,network,ipCidrRange)"

echo ""
echo "=== VPC Connector fix complete! ==="
echo ""
echo "Now you can commit and push the changes to trigger the deployment:"
echo "git add . && git commit -m 'Re-enable VPC connector for PRE environment' && git push origin pre"