#!/bin/bash

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"

echo "=== Final fix for VPC Connector ==="
echo ""

# Step 1: Enable Private Google Access on subnet
echo "Step 1: Enabling Private Google Access on subnet..."
gcloud compute networks subnets update nexus-subnet-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --enable-private-ip-google-access

echo ""
echo "Step 2: Delete the failed VPC connector..."
gcloud compute networks vpc-access connectors delete nexus-connector-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --quiet --async || echo "Connector might not exist"

echo ""
echo "Waiting 60 seconds for cleanup..."
sleep 60

echo ""
echo "Step 3: Create new VPC connector with correct configuration..."
gcloud compute networks vpc-access connectors create nexus-connector-pre \
  --region=$REGION \
  --subnet=nexus-subnet-pre \
  --subnet-project=$PROJECT_ID \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro \
  --project=$PROJECT_ID

echo ""
echo "Step 4: Check the status..."
gcloud compute networks vpc-access connectors describe nexus-connector-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="table(name,state,network,ipCidrRange)"

echo ""
echo "=== Fix complete! ==="
echo ""
echo "To monitor the VPC connector status, run:"
echo "watch -n 5 'gcloud compute networks vpc-access connectors describe nexus-connector-pre --region=europe-west1 --project=nexusdocs360-pre --format=\"table(name,state)\"'"