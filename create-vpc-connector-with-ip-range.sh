#!/bin/bash

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"

echo "=== Creating VPC Connector with specific IP range ==="
echo ""

# First check if old connector is deleted
echo "Checking connector status..."
STATUS=$(gcloud compute networks vpc-access connectors describe nexus-connector-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="value(state)" 2>/dev/null || echo "NOT_FOUND")

if [ "$STATUS" != "NOT_FOUND" ]; then
  echo "Connector still exists in state: $STATUS"
  echo "Waiting for deletion..."
  sleep 30
fi

echo ""
echo "Creating VPC connector with specific IP range..."
# Using a /28 range within the subnet that shouldn't conflict
gcloud compute networks vpc-access connectors create nexus-connector-pre \
  --region=$REGION \
  --subnet=nexus-subnet-pre \
  --subnet-project=$PROJECT_ID \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro \
  --project=$PROJECT_ID \
  --range=10.1.0.0/28

echo ""
echo "Checking status..."
gcloud compute networks vpc-access connectors describe nexus-connector-pre \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="table(name,state,ipCidrRange)"