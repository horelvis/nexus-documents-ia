#!/bin/bash

# Script to remove VPC connector from Cloud Run services in PRE environment

echo "Removing VPC connector from Cloud Run services..."

# Update backend service to remove VPC connector
echo "Updating nexus-backend-pre..."
gcloud run services update nexus-backend-pre \
  --region=europe-west1 \
  --project=nexusdocs360-pre \
  --clear-vpc-connector \
  --update-env-vars="DUMMY=1" \
  --remove-env-vars="DUMMY"

# Update storage service to remove VPC connector
echo "Updating storage-service-pre..."
gcloud run services update storage-service-pre \
  --region=europe-west1 \
  --project=nexusdocs360-pre \
  --clear-vpc-connector \
  --update-env-vars="DUMMY=1" \
  --remove-env-vars="DUMMY" 2>/dev/null || echo "Storage service might not exist yet"

echo "VPC connector removal complete!"
echo ""
echo "You can now re-run the GitHub Actions workflow."