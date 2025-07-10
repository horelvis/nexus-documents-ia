#!/bin/bash

# Enable public IP for Cloud SQL instance in PRE environment

echo "Enabling public IP for Cloud SQL instance..."

# Enable public IP
gcloud sql instances patch nexus-db-pre \
  --project=nexusdocs360-pre \
  --assign-ip \
  --authorized-networks=0.0.0.0/0 \
  --quiet

echo "Waiting for operation to complete..."
sleep 30

# Get the new public IP
PUBLIC_IP=$(gcloud sql instances describe nexus-db-pre --project=nexusdocs360-pre --format="value(ipAddresses[0].ipAddress)")

echo "Cloud SQL public IP enabled: $PUBLIC_IP"
echo ""
echo "IMPORTANT: Update your DATABASE_URL secret to use this public IP:"
echo "postgresql://nexus_user:password@$PUBLIC_IP:5432/nexus_db_pre"
echo ""
echo "For better security, later you should:"
echo "1. Restrict authorized networks to only Cloud Run IPs"
echo "2. Or use Cloud SQL Auth Proxy"