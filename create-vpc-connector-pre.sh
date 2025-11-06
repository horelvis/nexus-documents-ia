#!/bin/bash

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
VPC_NAME="nexus-vpc-pre"
SUBNET_NAME="nexus-subnet-pre"
CONNECTOR_NAME="nexus-connector-pre"

echo "Creating VPC Connector for PRE environment..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "VPC: $VPC_NAME"
echo "Subnet: $SUBNET_NAME"
echo ""

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable vpcaccess.googleapis.com --project=$PROJECT_ID

# Check if connector already exists
echo "Checking if VPC connector already exists..."
EXISTING_CONNECTOR=$(gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  2>/dev/null)

if [ -n "$EXISTING_CONNECTOR" ]; then
  echo "VPC connector already exists. Deleting it first..."
  gcloud compute networks vpc-access connectors delete $CONNECTOR_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --quiet
  echo "Waiting for deletion to complete..."
  sleep 30
fi

# Create VPC connector
echo "Creating VPC connector..."
gcloud compute networks vpc-access connectors create $CONNECTOR_NAME \
  --region=$REGION \
  --subnet=$SUBNET_NAME \
  --subnet-project=$PROJECT_ID \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro \
  --project=$PROJECT_ID

# Verify creation
echo ""
echo "Verifying VPC connector creation..."
gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="table(name,state,minThroughput,maxThroughput)"

echo ""
echo "VPC Connector created successfully!"
echo ""
echo "Now updating deploy-pre.yml to include VPC connector..."